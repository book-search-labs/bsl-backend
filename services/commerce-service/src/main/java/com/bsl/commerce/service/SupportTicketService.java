package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.SupportTicketRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupportTicketService {
    private static final Set<String> ALLOWED_CATEGORIES = Set.of("GENERAL", "ORDER", "SHIPPING", "REFUND", "PAYMENT", "ACCOUNT");
    private static final Set<String> ALLOWED_SEVERITIES = Set.of("LOW", "MEDIUM", "HIGH", "CRITICAL");
    private static final Set<String> ALLOWED_STATUSES = Set.of("RECEIVED", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED");
    private static final Set<String> RESOLVED_STATUSES = Set.of("RESOLVED", "CLOSED");

    private final SupportTicketRepository supportTicketRepository;
    private final OrderRepository orderRepository;
    private final ObjectMapper objectMapper;

    public SupportTicketService(
        SupportTicketRepository supportTicketRepository,
        OrderRepository orderRepository,
        ObjectMapper objectMapper
    ) {
        this.supportTicketRepository = supportTicketRepository;
        this.orderRepository = orderRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createTicket(long userId, TicketCreateRequest request) {
        if (request == null || request.summary() == null || request.summary().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "summary is required");
        }
        String category = normalizeCategory(request.category());
        String severity = normalizeSeverity(request.severity());
        Long orderId = request.orderId();
        if (orderId != null) {
            validateOrderOwnership(userId, orderId);
        }

        String ticketNo = generateTicketNo();
        String status = "RECEIVED";
        Timestamp expectedResponseAt = Timestamp.from(Instant.now().plus(Duration.ofMinutes(expectedResponseMinutes(severity))));

        long ticketId = supportTicketRepository.insertTicket(
            ticketNo,
            userId,
            orderId,
            category,
            severity,
            status,
            request.summary().trim(),
            JsonUtils.toJson(objectMapper, request.details()),
            normalizeOptional(request.errorCode()),
            normalizeOptional(request.chatSessionId()),
            normalizeOptional(request.chatRequestId()),
            expectedResponseAt
        );

        supportTicketRepository.insertTicketEvent(
            ticketId,
            "TICKET_RECEIVED",
            null,
            status,
            "ticket created",
            JsonUtils.toJson(objectMapper, Map.of("severity", severity, "category", category))
        );

        return supportTicketRepository.findTicketById(ticketId);
    }

    public Map<String, Object> getTicketByIdForUser(long userId, long ticketId) {
        Map<String, Object> ticket = supportTicketRepository.findTicketById(ticketId);
        ensureReadableByUser(ticket, userId);
        return ticket;
    }

    public Map<String, Object> getTicketByNoForUser(long userId, String ticketNo) {
        if (ticketNo == null || ticketNo.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "ticket_no is required");
        }
        Map<String, Object> ticket = supportTicketRepository.findTicketByNo(ticketNo.trim());
        ensureReadableByUser(ticket, userId);
        return ticket;
    }

    public List<Map<String, Object>> listTicketsForUser(long userId, Integer limit) {
        int resolvedLimit = 20;
        if (limit != null) {
            resolvedLimit = Math.min(Math.max(limit, 1), 100);
        }
        return supportTicketRepository.listTicketsByUser(userId, resolvedLimit);
    }

    public List<Map<String, Object>> listTicketEventsForUser(long userId, long ticketId) {
        Map<String, Object> ticket = supportTicketRepository.findTicketById(ticketId);
        ensureReadableByUser(ticket, userId);
        return supportTicketRepository.listTicketEvents(ticketId);
    }

    @Transactional
    public Map<String, Object> updateStatusAsAdmin(long ticketId, String nextStatus, String note) {
        Map<String, Object> ticket = supportTicketRepository.findTicketById(ticketId);
        if (ticket == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "ticket not found");
        }

        String normalized = normalizeStatus(nextStatus);
        String fromStatus = JdbcUtils.asString(ticket.get("status"));
        Timestamp resolvedAt = RESOLVED_STATUSES.contains(normalized) ? Timestamp.from(Instant.now()) : null;

        supportTicketRepository.updateStatus(ticketId, normalized, resolvedAt);
        supportTicketRepository.insertTicketEvent(
            ticketId,
            "STATUS_CHANGED",
            fromStatus,
            normalized,
            normalizeOptional(note),
            JsonUtils.toJson(objectMapper, Map.of("from", fromStatus, "to", normalized))
        );
        return supportTicketRepository.findTicketById(ticketId);
    }

    public int estimateResponseMinutes(Map<String, Object> ticket) {
        if (ticket == null) {
            return 0;
        }
        String severity = JdbcUtils.asString(ticket.get("severity"));
        return expectedResponseMinutes(normalizeSeverity(severity));
    }

    private void validateOrderOwnership(long userId, long orderId) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "order not found");
        }
        long orderUserId = JdbcUtils.asLong(order.get("user_id"));
        if (orderUserId != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "해당 주문의 티켓을 생성할 수 없습니다.");
        }
    }

    private void ensureReadableByUser(Map<String, Object> ticket, long userId) {
        if (ticket == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "ticket not found");
        }
        long ownerId = JdbcUtils.asLong(ticket.get("user_id"));
        if (ownerId != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "해당 티켓에 접근할 수 없습니다.");
        }
    }

    private String normalizeCategory(String category) {
        if (category == null || category.isBlank()) {
            return "GENERAL";
        }
        String normalized = category.trim().toUpperCase(Locale.ROOT);
        if (!ALLOWED_CATEGORIES.contains(normalized)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "invalid category");
        }
        return normalized;
    }

    private String normalizeSeverity(String severity) {
        if (severity == null || severity.isBlank()) {
            return "MEDIUM";
        }
        String normalized = severity.trim().toUpperCase(Locale.ROOT);
        if (!ALLOWED_SEVERITIES.contains(normalized)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "invalid severity");
        }
        return normalized;
    }

    private String normalizeStatus(String status) {
        if (status == null || status.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "status is required");
        }
        String normalized = status.trim().toUpperCase(Locale.ROOT);
        if (!ALLOWED_STATUSES.contains(normalized)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "invalid status");
        }
        return normalized;
    }

    private int expectedResponseMinutes(String severity) {
        return switch (severity) {
            case "CRITICAL" -> 30;
            case "HIGH" -> 60;
            case "LOW" -> 720;
            default -> 240;
        };
    }

    private String generateTicketNo() {
        String timestamp = java.time.format.DateTimeFormatter.ofPattern("yyyyMMddHHmmss")
            .withZone(java.time.ZoneId.of("Asia/Seoul"))
            .format(Instant.now());
        int rand = ThreadLocalRandom.current().nextInt(1000, 9999);
        return "STK" + timestamp + rand;
    }

    private String normalizeOptional(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    public record TicketCreateRequest(
        Long orderId,
        String category,
        String severity,
        String summary,
        Map<String, Object> details,
        String errorCode,
        String chatSessionId,
        String chatRequestId
    ) {
    }
}
