package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class CartRepository {
    private final JdbcTemplate jdbcTemplate;

    public CartRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findCartByUserId(long userId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT cart_id, user_id, status, created_at, updated_at FROM cart WHERE user_id = ?",
            userId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findCartById(long cartId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT cart_id, user_id, status, created_at, updated_at FROM cart WHERE cart_id = ?",
            cartId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertCart(long userId) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO cart (user_id, status) VALUES (?, 'ACTIVE')",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, userId);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void touchCart(long cartId) {
        jdbcTemplate.update(
            "UPDATE cart SET updated_at = CURRENT_TIMESTAMP WHERE cart_id = ?",
            cartId
        );
    }

    public List<Map<String, Object>> listCartItems(long cartId) {
        return jdbcTemplate.queryForList(
            "SELECT cart_item_id, cart_id, sku_id, seller_id, qty, offer_id, unit_price, currency, captured_at, added_at, "
                + "updated_at FROM cart_item WHERE cart_id = ? ORDER BY cart_item_id DESC",
            cartId
        );
    }

    public Map<String, Object> findCartItemById(long cartItemId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT cart_item_id, cart_id, sku_id, seller_id, qty, offer_id, unit_price, currency, captured_at, added_at, "
                + "updated_at FROM cart_item WHERE cart_item_id = ?",
            cartItemId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void upsertCartItem(
        long cartId,
        long skuId,
        long sellerId,
        int qty,
        Long offerId,
        Integer unitPrice,
        String currency,
        java.time.Instant capturedAt
    ) {
        jdbcTemplate.update(
            "INSERT INTO cart_item (cart_id, sku_id, seller_id, qty, offer_id, unit_price, currency, captured_at) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                + "ON DUPLICATE KEY UPDATE qty = VALUES(qty), offer_id = VALUES(offer_id), unit_price = VALUES(unit_price), "
                + "currency = VALUES(currency), captured_at = VALUES(captured_at), updated_at = CURRENT_TIMESTAMP",
            cartId,
            skuId,
            sellerId,
            qty,
            offerId,
            unitPrice,
            currency,
            capturedAt == null ? null : java.sql.Timestamp.from(capturedAt)
        );
    }

    public void updateCartItemQty(
        long cartItemId,
        int qty,
        Long offerId,
        Integer unitPrice,
        String currency,
        java.time.Instant capturedAt
    ) {
        jdbcTemplate.update(
            "UPDATE cart_item SET qty = ?, offer_id = ?, unit_price = ?, currency = ?, captured_at = ?, "
                + "updated_at = CURRENT_TIMESTAMP WHERE cart_item_id = ?",
            qty,
            offerId,
            unitPrice,
            currency,
            capturedAt == null ? null : java.sql.Timestamp.from(capturedAt),
            cartItemId
        );
    }

    public void deleteCartItem(long cartItemId) {
        jdbcTemplate.update("DELETE FROM cart_item WHERE cart_item_id = ?", cartItemId);
    }

    public void clearCart(long cartId) {
        jdbcTemplate.update("DELETE FROM cart_item WHERE cart_id = ?", cartId);
    }

    public int countDistinctItems(long cartId) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM cart_item WHERE cart_id = ?",
            Integer.class,
            cartId
        );
        return count == null ? 0 : count;
    }
}
