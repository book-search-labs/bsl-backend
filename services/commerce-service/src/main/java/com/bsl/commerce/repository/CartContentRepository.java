package com.bsl.commerce.repository;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CartContentRepository {
    private static final String TABLE_CART_CONTENT_ITEM = "cart_content_item";

    private final JdbcTemplate jdbcTemplate;
    private volatile Boolean cartContentTableExists;

    public CartContentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listActiveByType(String type, int limit) {
        if (!hasCartContentTable()) {
            return List.of();
        }
        return jdbcTemplate.queryForList(
            "SELECT item_id, content_type, title, description, sort_order "
                + "FROM cart_content_item "
                + "WHERE content_type = ? AND is_active = 1 "
                + "ORDER BY sort_order ASC, item_id ASC LIMIT ?",
            type,
            limit
        );
    }

    private boolean hasCartContentTable() {
        Boolean cached = cartContentTableExists;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (cartContentTableExists != null) {
                return cartContentTableExists;
            }
            try {
                Integer count = jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM information_schema.tables "
                        + "WHERE table_schema = DATABASE() AND table_name = ?",
                    Integer.class,
                    TABLE_CART_CONTENT_ITEM
                );
                cartContentTableExists = count != null && count > 0;
            } catch (Exception ex) {
                cartContentTableExists = false;
            }
            return cartContentTableExists;
        }
    }
}
