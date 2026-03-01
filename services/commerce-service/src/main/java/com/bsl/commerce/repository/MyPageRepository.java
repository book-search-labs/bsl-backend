package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class MyPageRepository {
    private final JdbcTemplate jdbcTemplate;

    public MyPageRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listWishlist(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT usm.material_id, usm.created_at, "
                + "COALESCE(NULLIF(TRIM(m.title), ''), NULLIF(TRIM(m.label), ''), usm.material_id) AS title, "
                + "authors.author_name AS author "
                + "FROM user_saved_material usm "
                + "LEFT JOIN material m ON m.material_id = usm.material_id "
                + "LEFT JOIN ("
                + "  SELECT ma.material_id, MIN(COALESCE(NULLIF(TRIM(a.pref_label), ''), NULLIF(TRIM(a.label), ''), a.name)) AS author_name "
                + "  FROM material_agent ma "
                + "  JOIN agent a ON a.agent_id = ma.agent_id "
                + "  WHERE ma.role = 'AUTHOR' "
                + "  GROUP BY ma.material_id"
                + ") authors ON authors.material_id = usm.material_id "
                + "WHERE usm.user_id = ? "
                + "ORDER BY usm.created_at DESC",
            userId
        );
    }

    public void addWishlist(long userId, String materialId) {
        jdbcTemplate.update(
            "INSERT IGNORE INTO user_saved_material (user_id, material_id) VALUES (?, ?)",
            userId,
            materialId
        );
    }

    public int removeWishlist(long userId, String materialId) {
        return jdbcTemplate.update(
            "DELETE FROM user_saved_material WHERE user_id = ? AND material_id = ?",
            userId,
            materialId
        );
    }

    public List<Map<String, Object>> listComments(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT comment_id, user_id, order_id, title, rating, content, created_at "
                + "FROM my_comment WHERE user_id = ? ORDER BY comment_id DESC",
            userId
        );
    }

    public boolean existsCommentByUserAndOrder(long userId, long orderId) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM my_comment WHERE user_id = ? AND order_id = ?",
            Integer.class,
            userId,
            orderId
        );
        return count != null && count > 0;
    }

    public long insertComment(long userId, long orderId, String title, int rating, String content) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO my_comment (user_id, order_id, title, rating, content) VALUES (?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, userId);
            ps.setLong(2, orderId);
            ps.setString(3, title);
            ps.setInt(4, rating);
            ps.setString(5, content);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public Map<String, Object> findCommentById(long commentId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT comment_id, user_id, order_id, title, rating, content, created_at "
                + "FROM my_comment WHERE comment_id = ?",
            commentId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listPointLogs(long userId, int limit) {
        return jdbcTemplate.queryForList(
            "SELECT ledger_id, type, delta, reason, created_at "
                + "FROM loyalty_point_ledger WHERE user_id = ? ORDER BY ledger_id DESC LIMIT ?",
            userId,
            limit
        );
    }

    public List<Map<String, Object>> listVouchers(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT voucher_id, name, value, expires_at, used, used_at "
                + "FROM my_voucher WHERE user_id = ? ORDER BY voucher_id DESC",
            userId
        );
    }

    public List<Map<String, Object>> listCoupons(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT coupon_id, name, discount_label, expires_at, usable "
                + "FROM my_coupon WHERE user_id = ? ORDER BY coupon_id DESC",
            userId
        );
    }

    public List<Map<String, Object>> listELibraryBooks(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT entry_id, material_id, title, author, publisher, downloaded_at, drm_policy, cover_url "
                + "FROM my_ebook_library WHERE user_id = ? ORDER BY downloaded_at DESC",
            userId
        );
    }

    public void ensureNotificationPreferences(long userId) {
        jdbcTemplate.update(
            "INSERT IGNORE INTO my_notification_preference (user_id, category, label, enabled) VALUES "
                + "(?, 'order', '주문/배송 알림', 1), "
                + "(?, 'event', '이벤트 알림', 1), "
                + "(?, 'benefit', '혜택 알림', 1), "
                + "(?, 'system', '서비스 알림', 1)",
            userId,
            userId,
            userId,
            userId
        );
    }

    public List<Map<String, Object>> listNotificationPreferences(long userId) {
        ensureNotificationPreferences(userId);
        return jdbcTemplate.queryForList(
            "SELECT category, label, enabled, updated_at "
                + "FROM my_notification_preference WHERE user_id = ? ORDER BY category",
            userId
        );
    }

    public void updateNotificationPreference(long userId, String category, boolean enabled) {
        ensureNotificationPreferences(userId);
        jdbcTemplate.update(
            "UPDATE my_notification_preference SET enabled = ?, updated_at = CURRENT_TIMESTAMP "
                + "WHERE user_id = ? AND category = ?",
            enabled,
            userId,
            category
        );
    }

    public List<Map<String, Object>> listNotifications(long userId, String category, boolean unreadOnly, int limit) {
        StringBuilder sql = new StringBuilder(
            "SELECT notification_id, category, title, body, is_read, created_at "
                + "FROM my_notification WHERE user_id = ?"
        );
        List<Object> args = new ArrayList<>();
        args.add(userId);

        if (category != null && !category.isBlank()) {
            sql.append(" AND category = ?");
            args.add(category);
        }
        if (unreadOnly) {
            sql.append(" AND is_read = 0");
        }

        sql.append(" ORDER BY notification_id DESC LIMIT ?");
        args.add(limit);

        return jdbcTemplate.queryForList(sql.toString(), args.toArray());
    }

    public int markNotificationRead(long userId, long notificationId) {
        return jdbcTemplate.update(
            "UPDATE my_notification SET is_read = 1, read_at = CURRENT_TIMESTAMP "
                + "WHERE user_id = ? AND notification_id = ?",
            userId,
            notificationId
        );
    }

    public int markAllNotificationsRead(long userId) {
        return jdbcTemplate.update(
            "UPDATE my_notification SET is_read = 1, read_at = CURRENT_TIMESTAMP "
                + "WHERE user_id = ? AND is_read = 0",
            userId
        );
    }

    public List<Map<String, Object>> listGifts(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT gift_id, title, status, direction, partner_name, message, gift_code, expires_at, created_at "
                + "FROM my_gift WHERE user_id = ? ORDER BY created_at DESC",
            userId
        );
    }

    public Map<String, Object> findGiftById(long userId, String giftId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT gift_id, title, status, direction, partner_name, message, gift_code, expires_at, created_at "
                + "FROM my_gift WHERE user_id = ? AND gift_id = ?",
            userId,
            giftId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listGiftItems(String giftId) {
        return jdbcTemplate.queryForList(
            "SELECT gift_item_id, material_id, title, author, publisher, quantity, unit_price, cover_url "
                + "FROM my_gift_item WHERE gift_id = ? ORDER BY gift_item_id",
            giftId
        );
    }
}
