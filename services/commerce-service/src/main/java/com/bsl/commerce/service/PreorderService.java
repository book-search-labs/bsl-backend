package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.PreorderRepository;
import java.text.NumberFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PreorderService {
    private static final int DEFAULT_LIMIT = 12;
    private static final int MAX_LIMIT = 60;
    private static final int DEFAULT_QTY = 1;
    private static final int MAX_QTY = 10;
    private static final NumberFormat KOREA_NUMBER = NumberFormat.getNumberInstance(Locale.KOREA);

    private final PreorderRepository preorderRepository;

    public PreorderService(PreorderRepository preorderRepository) {
        this.preorderRepository = preorderRepository;
    }

    public QueryOptions resolveQuery(Integer limit) {
        int resolvedLimit = limit == null ? DEFAULT_LIMIT : Math.min(Math.max(limit, 1), MAX_LIMIT);
        return new QueryOptions(resolvedLimit);
    }

    public List<Map<String, Object>> listActivePreorders(long userId, QueryOptions options) {
        return preorderRepository.listActiveItems(userId, options.limit()).stream()
            .map(this::toPreorderItem)
            .toList();
    }

    public long countActivePreorders() {
        return preorderRepository.countActiveItems();
    }

    @Transactional
    public Map<String, Object> reserve(long userId, long preorderId, ReserveRequest request) {
        int qty = request == null || request.qty() == null ? DEFAULT_QTY : request.qty();
        if (qty < 1 || qty > MAX_QTY) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty must be between 1 and 10");
        }

        Map<String, Object> preorder = preorderRepository.findActiveItemById(preorderId);
        if (preorder == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "preorder item not found");
        }

        Map<String, Object> existing = preorderRepository.findUserReservation(preorderId, userId);
        int existingQty = existing == null ? 0 : Math.max(0, JdbcUtils.asInt(existing.get("qty")) == null ? 0 : JdbcUtils.asInt(existing.get("qty")));
        int reservedTotal = preorderRepository.countReservedQty(preorderId);
        Integer reservationLimit = JdbcUtils.asInt(preorder.get("reservation_limit"));

        int nextReservedTotal = reservedTotal - existingQty + qty;
        if (reservationLimit != null && reservationLimit > 0 && nextReservedTotal > reservationLimit) {
            throw new ApiException(HttpStatus.CONFLICT, "preorder_limit_exceeded", "예약 가능 수량이 부족합니다.");
        }

        Integer preorderPrice = JdbcUtils.asInt(preorder.get("preorder_price"));
        int reservedPrice = preorderPrice == null ? 0 : preorderPrice;
        String note = request == null ? null : request.note();

        long reservationId;
        if (existing == null) {
            reservationId = preorderRepository.insertReservation(preorderId, userId, qty, reservedPrice, note);
        } else {
            reservationId = JdbcUtils.asLong(existing.get("reservation_id")) == null ? 0L : JdbcUtils.asLong(existing.get("reservation_id"));
            preorderRepository.updateReservation(reservationId, qty, reservedPrice, note);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reservation_id", reservationId);
        result.put("preorder_id", preorderId);
        result.put("user_id", userId);
        result.put("qty", qty);
        result.put("status", "RESERVED");
        result.put("reserved_price", reservedPrice);
        result.put("reserved_price_label", formatCurrency(reservedPrice));
        result.put("reservation_limit", reservationLimit);
        result.put("reserved_total", nextReservedTotal);
        result.put("remaining", reservationLimit == null ? null : Math.max(0, reservationLimit - nextReservedTotal));
        result.put("note", note);
        return result;
    }

    private Map<String, Object> toPreorderItem(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        String title = JdbcUtils.asString(row.get("title_ko"));
        String authorName = JdbcUtils.asString(row.get("author_name"));
        Integer preorderPrice = JdbcUtils.asInt(row.get("preorder_price"));
        Integer listPrice = JdbcUtils.asInt(row.get("list_price"));
        Integer discountRate = JdbcUtils.asInt(row.get("discount_rate"));
        Integer reservationLimit = JdbcUtils.asInt(row.get("reservation_limit"));
        Integer reservedCount = JdbcUtils.asInt(row.get("reserved_count"));
        Integer reservedQty = JdbcUtils.asInt(row.get("reserved_qty"));

        item.put("preorder_id", JdbcUtils.asLong(row.get("preorder_id")));
        item.put("doc_id", JdbcUtils.asString(row.get("material_id")));
        item.put("title_ko", title);
        item.put("authors", authorName == null || authorName.isBlank() ? List.of() : List.of(authorName));
        item.put("publisher_name", JdbcUtils.asString(row.get("publisher_name")));
        item.put("issued_year", JdbcUtils.asInt(row.get("issued_year")));
        item.put("subtitle", JdbcUtils.asString(row.get("subtitle")));
        item.put("summary", JdbcUtils.asString(row.get("summary")));
        item.put("badge", JdbcUtils.asString(row.get("badge")));
        item.put("cta_label", JdbcUtils.asString(row.get("cta_label")));
        item.put("preorder_price", preorderPrice);
        item.put("preorder_price_label", formatCurrency(preorderPrice));
        item.put("list_price", listPrice);
        item.put("list_price_label", formatCurrency(listPrice));
        item.put("discount_rate", discountRate);
        item.put("preorder_start_at", JdbcUtils.asIsoString(row.get("preorder_start_at")));
        item.put("preorder_end_at", JdbcUtils.asIsoString(row.get("preorder_end_at")));
        item.put("release_at", JdbcUtils.asIsoString(row.get("release_at")));
        item.put("reservation_limit", reservationLimit);
        item.put("reserved_count", reservedCount == null ? 0 : reservedCount);
        item.put("remaining", reservationLimit == null
            ? null
            : Math.max(0, reservationLimit - (reservedCount == null ? 0 : reservedCount)));
        item.put("reserved_by_me", (JdbcUtils.asInt(row.get("reserved_by_me")) == null ? 0 : JdbcUtils.asInt(row.get("reserved_by_me"))) == 1);
        item.put("reserved_qty", reservedQty == null ? 0 : reservedQty);
        return item;
    }

    private String formatCurrency(Integer amount) {
        if (amount == null) {
            return null;
        }
        return KOREA_NUMBER.format(amount) + "원";
    }

    public record QueryOptions(int limit) {
    }

    public record ReserveRequest(Integer qty, String note) {
    }
}
