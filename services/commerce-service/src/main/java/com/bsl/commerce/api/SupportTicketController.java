package com.bsl.commerce.api;

import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.SupportTicketService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping
public class SupportTicketController {
    private final SupportTicketService supportTicketService;

    public SupportTicketController(SupportTicketService supportTicketService) {
        this.supportTicketService = supportTicketService;
    }

    @PostMapping("/api/v1/support/tickets")
    public Map<String, Object> createTicket(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody TicketCreateRequest request
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        SupportTicketService.TicketCreateRequest createRequest = new SupportTicketService.TicketCreateRequest(
            request.orderId,
            request.category,
            request.severity,
            request.summary,
            request.details,
            request.errorCode,
            request.chatSessionId,
            request.chatRequestId
        );
        Map<String, Object> ticket = supportTicketService.createTicket(userId, createRequest);

        Map<String, Object> response = base();
        response.put("ticket", ticket);
        response.put("expected_response_minutes", supportTicketService.estimateResponseMinutes(ticket));
        return response;
    }

    @GetMapping("/api/v1/support/tickets/{ticketId}")
    public Map<String, Object> getTicketById(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long ticketId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> ticket = supportTicketService.getTicketByIdForUser(userId, ticketId);
        Map<String, Object> response = base();
        response.put("ticket", ticket);
        response.put("expected_response_minutes", supportTicketService.estimateResponseMinutes(ticket));
        return response;
    }

    @GetMapping("/api/v1/support/tickets/by-number/{ticketNo}")
    public Map<String, Object> getTicketByNo(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable String ticketNo
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> ticket = supportTicketService.getTicketByNoForUser(userId, ticketNo);
        Map<String, Object> response = base();
        response.put("ticket", ticket);
        response.put("expected_response_minutes", supportTicketService.estimateResponseMinutes(ticket));
        return response;
    }

    @GetMapping("/api/v1/support/tickets")
    public Map<String, Object> listTickets(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestParam(name = "limit", required = false) Integer limit
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> tickets = supportTicketService.listTicketsForUser(userId, limit);

        Map<String, Object> response = base();
        response.put("items", tickets);
        response.put("count", tickets.size());
        return response;
    }

    @GetMapping("/api/v1/support/tickets/{ticketId}/events")
    public Map<String, Object> listTicketEvents(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long ticketId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        List<Map<String, Object>> events = supportTicketService.listTicketEventsForUser(userId, ticketId);

        Map<String, Object> response = base();
        response.put("items", events);
        response.put("count", events.size());
        return response;
    }

    @PostMapping("/admin/support/tickets/{ticketId}/status")
    public Map<String, Object> updateStatus(
        @RequestHeader(value = "x-admin-id", required = false) String adminIdHeader,
        @PathVariable long ticketId,
        @RequestBody TicketStatusRequest request
    ) {
        RequestUtils.resolveAdminId(adminIdHeader, 1L);
        Map<String, Object> ticket = supportTicketService.updateStatusAsAdmin(ticketId, request.status, request.note);

        Map<String, Object> response = base();
        response.put("ticket", ticket);
        response.put("expected_response_minutes", supportTicketService.estimateResponseMinutes(ticket));
        return response;
    }

    private Map<String, Object> base() {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new HashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        return response;
    }

    public static class TicketCreateRequest {
        public Long orderId;
        public String category;
        public String severity;
        public String summary;
        public Map<String, Object> details;
        public String errorCode;
        public String chatSessionId;
        public String chatRequestId;
    }

    public static class TicketStatusRequest {
        public String status;
        public String note;
    }
}
