package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.MyPageRepository;
import com.bsl.commerce.repository.OrderRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MyPageService {
    private static final Set<String> ALLOWED_NOTIFICATION_CATEGORIES = Set.of("order", "event", "benefit", "system");
    private static final Set<String> ALLOWED_REVIEW_ORDER_STATUSES = Set.of("DELIVERED", "PURCHASE_CONFIRMED", "COMPLETED");

    private final MyPageRepository myPageRepository;
    private final CatalogService catalogService;
    private final SupportTicketService supportTicketService;
    private final OrderRepository orderRepository;
    private final LoyaltyPointService loyaltyPointService;
    private final ObjectMapper objectMapper;

    public MyPageService(
        MyPageRepository myPageRepository,
        CatalogService catalogService,
        SupportTicketService supportTicketService,
        OrderRepository orderRepository,
        LoyaltyPointService loyaltyPointService,
        ObjectMapper objectMapper
    ) {
        this.myPageRepository = myPageRepository;
        this.catalogService = catalogService;
        this.supportTicketService = supportTicketService;
        this.orderRepository = orderRepository;
        this.loyaltyPointService = loyaltyPointService;
        this.objectMapper = objectMapper;
    }

    public List<Map<String, Object>> listWishlist(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listWishlist(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            String docId = JdbcUtils.asString(row.get("material_id"));
            Map<String, Object> offer = docId == null ? null : catalogService.getCurrentOfferByMaterialId(docId);
            Integer price = offer == null ? null : JdbcUtils.asInt(offer.get("effective_price"));

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", docId);
            item.put("docId", docId);
            item.put("title", JdbcUtils.asString(row.get("title")));
            item.put("author", blankToFallback(JdbcUtils.asString(row.get("author")), "저자 정보 없음"));
            item.put("coverUrl", null);
            item.put("price", price == null ? 0 : price);
            items.add(item);
        }
        return items;
    }

    @Transactional
    public Map<String, Object> addWishlist(long userId, String docId) {
        if (docId == null || docId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "docId is required");
        }
        myPageRepository.addWishlist(userId, docId.trim());
        return listWishlist(userId).stream()
            .filter(item -> docId.trim().equals(item.get("docId")))
            .findFirst()
            .orElseGet(() -> {
                Map<String, Object> fallback = new LinkedHashMap<>();
                fallback.put("id", docId.trim());
                fallback.put("docId", docId.trim());
                fallback.put("title", docId.trim());
                fallback.put("author", "저자 정보 없음");
                fallback.put("coverUrl", null);
                fallback.put("price", 0);
                return fallback;
            });
    }

    @Transactional
    public List<Map<String, Object>> removeWishlist(long userId, String docId) {
        if (docId == null || docId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "docId is required");
        }
        myPageRepository.removeWishlist(userId, docId.trim());
        return listWishlist(userId);
    }

    public List<Map<String, Object>> listComments(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listComments(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            items.add(toCommentDto(row));
        }
        return items;
    }

    @Transactional
    public Map<String, Object> addComment(long userId, CommentCreateRequest request) {
        if (request == null || request.orderId() == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "orderId is required");
        }
        if (request.content() == null || request.content().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "content is required");
        }
        if (request.rating() < 1 || request.rating() > 5) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "rating must be between 1 and 5");
        }

        Map<String, Object> order = orderRepository.findOrderById(request.orderId());
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "order not found");
        }

        Long owner = JdbcUtils.asLong(order.get("user_id"));
        if (owner == null || owner != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "해당 주문에 코멘트를 작성할 수 없습니다.");
        }

        String status = blankToFallback(JdbcUtils.asString(order.get("status")), "").toUpperCase(Locale.ROOT);
        if (!ALLOWED_REVIEW_ORDER_STATUSES.contains(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_order_status", "배송 완료 주문에서만 코멘트를 작성할 수 있습니다.");
        }

        if (myPageRepository.existsCommentByUserAndOrder(userId, request.orderId())) {
            throw new ApiException(HttpStatus.CONFLICT, "comment_exists", "이미 해당 주문의 코멘트를 작성했습니다.");
        }

        String title = blankToFallback(request.title(), "주문 #" + request.orderId());
        long commentId = myPageRepository.insertComment(userId, request.orderId(), title, request.rating(), request.content().trim());
        Map<String, Object> inserted = myPageRepository.findCommentById(commentId);
        if (inserted == null) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "internal_error", "comment insert failed");
        }
        return toCommentDto(inserted);
    }

    public Map<String, Object> getWalletPoints(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listPointLogs(userId, 200);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            String type = blankToFallback(JdbcUtils.asString(row.get("type")), "UNKNOWN");
            String reason = JdbcUtils.asString(row.get("reason"));
            Integer delta = JdbcUtils.asInt(row.get("delta"));

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", String.valueOf(JdbcUtils.asLong(row.get("ledger_id"))));
            item.put("description", blankToFallback(reason, resolvePointDescription(type, delta == null ? 0 : delta)));
            item.put("amount", delta == null ? 0 : delta);
            item.put("createdAt", JdbcUtils.asIsoString(row.get("created_at")));
            items.add(item);
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("balance", loyaltyPointService.getBalance(userId));
        response.put("items", items);
        return response;
    }

    public List<Map<String, Object>> listVouchers(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listVouchers(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", String.valueOf(JdbcUtils.asLong(row.get("voucher_id"))));
            item.put("name", JdbcUtils.asString(row.get("name")));
            item.put("value", JdbcUtils.asInt(row.get("value")));
            item.put("expiresAt", JdbcUtils.asString(row.get("expires_at")));
            item.put("used", asBoolean(row.get("used")));
            items.add(item);
        }
        return items;
    }

    public List<Map<String, Object>> listCoupons(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listCoupons(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", String.valueOf(JdbcUtils.asLong(row.get("coupon_id"))));
            item.put("name", JdbcUtils.asString(row.get("name")));
            item.put("discountLabel", JdbcUtils.asString(row.get("discount_label")));
            item.put("expiresAt", JdbcUtils.asString(row.get("expires_at")));
            item.put("usable", asBoolean(row.get("usable")));
            items.add(item);
        }
        return items;
    }

    public List<Map<String, Object>> listELibraryBooks(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listELibraryBooks(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            String docId = JdbcUtils.asString(row.get("material_id"));
            item.put("id", blankToFallback(docId, String.valueOf(JdbcUtils.asLong(row.get("entry_id")))));
            item.put("docId", docId);
            item.put("title", JdbcUtils.asString(row.get("title")));
            item.put("author", blankToFallback(JdbcUtils.asString(row.get("author")), "저자 정보 없음"));
            item.put("publisher", JdbcUtils.asString(row.get("publisher")));
            item.put("downloadedAt", JdbcUtils.asIsoString(row.get("downloaded_at")));
            item.put("drmPolicy", JdbcUtils.asString(row.get("drm_policy")));
            item.put("coverUrl", JdbcUtils.asString(row.get("cover_url")));
            items.add(item);
        }
        return items;
    }

    public List<Map<String, Object>> listNotifications(long userId, String category, boolean unreadOnly) {
        String normalizedCategory = normalizeNotificationCategory(category);
        List<Map<String, Object>> rows = myPageRepository.listNotifications(userId, normalizedCategory, unreadOnly, 300);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", String.valueOf(JdbcUtils.asLong(row.get("notification_id"))));
            item.put("category", JdbcUtils.asString(row.get("category")));
            item.put("title", JdbcUtils.asString(row.get("title")));
            item.put("body", JdbcUtils.asString(row.get("body")));
            item.put("createdAt", JdbcUtils.asIsoString(row.get("created_at")));
            item.put("read", asBoolean(row.get("is_read")));
            items.add(item);
        }
        return items;
    }

    public List<Map<String, Object>> listNotificationPreferences(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listNotificationPreferences(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("category", JdbcUtils.asString(row.get("category")));
            item.put("label", JdbcUtils.asString(row.get("label")));
            item.put("enabled", asBoolean(row.get("enabled")));
            items.add(item);
        }
        return items;
    }

    @Transactional
    public List<Map<String, Object>> setNotificationPreference(long userId, String category, boolean enabled) {
        String normalizedCategory = normalizeNotificationCategory(category == null ? null : category.toLowerCase(Locale.ROOT));
        if (normalizedCategory == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "category is required");
        }
        myPageRepository.updateNotificationPreference(userId, normalizedCategory, enabled);
        return listNotificationPreferences(userId);
    }

    @Transactional
    public void markNotificationRead(long userId, String notificationId) {
        long id = parseId(notificationId, "notificationId");
        int updated = myPageRepository.markNotificationRead(userId, id);
        if (updated <= 0) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "notification not found");
        }
    }

    @Transactional
    public int markAllNotificationsRead(long userId) {
        return myPageRepository.markAllNotificationsRead(userId);
    }

    public List<Map<String, Object>> listGifts(long userId) {
        List<Map<String, Object>> rows = myPageRepository.listGifts(userId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            Map<String, Object> item = toGiftSummaryDto(row);
            item.put("items", List.of());
            items.add(item);
        }
        return items;
    }

    public Map<String, Object> getGiftById(long userId, String giftId) {
        if (giftId == null || giftId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "giftId is required");
        }

        Map<String, Object> row = myPageRepository.findGiftById(userId, giftId.trim());
        if (row == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "gift not found");
        }

        Map<String, Object> detail = toGiftSummaryDto(row);
        detail.put("items", listGiftBookDtos(giftId.trim()));
        return detail;
    }

    public List<Map<String, Object>> listInquiries(long userId) {
        List<Map<String, Object>> tickets = supportTicketService.listTicketsForUser(userId, 100);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> ticket : tickets) {
            items.add(toInquiryDto(ticket));
        }
        return items;
    }

    @Transactional
    public Map<String, Object> createInquiry(long userId, InquiryCreateRequest request) {
        if (request == null || request.title() == null || request.title().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "title is required");
        }
        if (request.content() == null || request.content().isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "content is required");
        }

        String categoryCode = mapInquiryCategoryToSupportCategory(request.category());
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("content", request.content().trim());
        details.put("source", "MY_PAGE");

        Map<String, Object> ticket = supportTicketService.createTicket(
            userId,
            new SupportTicketService.TicketCreateRequest(
                null,
                categoryCode,
                "MEDIUM",
                request.title().trim(),
                details,
                null,
                null,
                null
            )
        );
        return toInquiryDto(ticket);
    }

    private List<Map<String, Object>> listGiftBookDtos(String giftId) {
        List<Map<String, Object>> books = myPageRepository.listGiftItems(giftId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> book : books) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("docId", JdbcUtils.asString(book.get("material_id")));
            item.put("title", JdbcUtils.asString(book.get("title")));
            item.put("author", blankToFallback(JdbcUtils.asString(book.get("author")), "저자 정보 없음"));
            item.put("publisher", JdbcUtils.asString(book.get("publisher")));
            item.put("quantity", JdbcUtils.asInt(book.get("quantity")));
            item.put("unitPrice", JdbcUtils.asInt(book.get("unit_price")));
            item.put("coverUrl", JdbcUtils.asString(book.get("cover_url")));
            items.add(item);
        }
        return items;
    }

    private Map<String, Object> toGiftSummaryDto(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", JdbcUtils.asString(row.get("gift_id")));
        item.put("title", JdbcUtils.asString(row.get("title")));
        item.put("status", JdbcUtils.asString(row.get("status")));
        item.put("createdAt", JdbcUtils.asIsoString(row.get("created_at")));
        item.put("direction", JdbcUtils.asString(row.get("direction")));
        item.put("partnerName", JdbcUtils.asString(row.get("partner_name")));
        item.put("message", JdbcUtils.asString(row.get("message")));
        item.put("giftCode", JdbcUtils.asString(row.get("gift_code")));
        item.put("expiresAt", JdbcUtils.asIsoString(row.get("expires_at")));
        return item;
    }

    private Map<String, Object> toCommentDto(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", String.valueOf(JdbcUtils.asLong(row.get("comment_id"))));
        item.put("orderId", JdbcUtils.asLong(row.get("order_id")));
        item.put("title", JdbcUtils.asString(row.get("title")));
        item.put("rating", JdbcUtils.asInt(row.get("rating")));
        item.put("content", JdbcUtils.asString(row.get("content")));
        item.put("createdAt", JdbcUtils.asIsoString(row.get("created_at")));
        return item;
    }

    private Map<String, Object> toInquiryDto(Map<String, Object> ticket) {
        Map<String, Object> item = new LinkedHashMap<>();
        String ticketId = String.valueOf(JdbcUtils.asLong(ticket.get("ticket_id")));
        String detailJson = JdbcUtils.asString(ticket.get("detail_json"));

        item.put("id", ticketId);
        item.put("title", JdbcUtils.asString(ticket.get("summary")));
        item.put("category", mapSupportCategoryToInquiryCategory(JdbcUtils.asString(ticket.get("category"))));
        item.put("content", extractInquiryContent(detailJson));
        item.put("status", mapSupportStatusToInquiryStatus(JdbcUtils.asString(ticket.get("status"))));
        item.put("createdAt", JdbcUtils.asIsoString(ticket.get("created_at")));
        return item;
    }

    private String extractInquiryContent(String detailJson) {
        if (detailJson == null || detailJson.isBlank()) {
            return "";
        }
        try {
            Map<String, Object> parsed = objectMapper.readValue(detailJson, new TypeReference<>() {
            });
            String content = JdbcUtils.asString(parsed.get("content"));
            return content == null ? "" : content;
        } catch (Exception ex) {
            return "";
        }
    }

    private String resolvePointDescription(String type, int delta) {
        return switch (type) {
            case "EARN" -> "주문 적립";
            case "SPEND" -> "포인트 사용";
            case "EXPIRE" -> "포인트 만료";
            case "ADJUST" -> delta >= 0 ? "포인트 조정(+)": "포인트 조정(-)";
            default -> "포인트 변동";
        };
    }

    private String normalizeNotificationCategory(String category) {
        if (category == null || category.isBlank() || "all".equalsIgnoreCase(category)) {
            return null;
        }
        String normalized = category.trim().toLowerCase(Locale.ROOT);
        if (!ALLOWED_NOTIFICATION_CATEGORIES.contains(normalized)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "invalid category");
        }
        return normalized;
    }

    private long parseId(String rawId, String field) {
        if (rawId == null || rawId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + " is required");
        }
        try {
            return Long.parseLong(rawId.trim());
        } catch (NumberFormatException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", field + " must be numeric");
        }
    }

    private boolean asBoolean(Object value) {
        if (value instanceof Boolean bool) {
            return bool;
        }
        if (value instanceof Number number) {
            return number.intValue() != 0;
        }
        if (value instanceof String str) {
            return "1".equals(str) || "true".equalsIgnoreCase(str);
        }
        return false;
    }

    private String blankToFallback(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.trim();
    }

    private String mapInquiryCategoryToSupportCategory(String category) {
        if (category == null || category.isBlank()) {
            return "GENERAL";
        }
        return switch (category.trim()) {
            case "주문/배송" -> "ORDER";
            case "결제/환불" -> "REFUND";
            case "쿠폰/혜택" -> "PAYMENT";
            case "계정/설정" -> "ACCOUNT";
            default -> "GENERAL";
        };
    }

    private String mapSupportCategoryToInquiryCategory(String category) {
        if (category == null || category.isBlank()) {
            return "기타";
        }
        return switch (category.trim().toUpperCase(Locale.ROOT)) {
            case "ORDER", "SHIPPING" -> "주문/배송";
            case "PAYMENT", "REFUND" -> "결제/환불";
            case "ACCOUNT" -> "계정/설정";
            default -> "기타";
        };
    }

    private String mapSupportStatusToInquiryStatus(String status) {
        if (status == null || status.isBlank()) {
            return "접수";
        }
        return switch (status.trim().toUpperCase(Locale.ROOT)) {
            case "RECEIVED" -> "접수";
            case "IN_PROGRESS", "WAITING_USER" -> "처리 중";
            case "RESOLVED", "CLOSED" -> "답변 완료";
            default -> "접수";
        };
    }

    public record CommentCreateRequest(Long orderId, String title, int rating, String content) {
    }

    public record InquiryCreateRequest(String title, String category, String content) {
    }
}
