package com.bsl.commerce.repository;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class PreorderRepository {
    private static final String TABLE_PREORDER_ITEM = "preorder_item";
    private static final String TABLE_PREORDER_RESERVATION = "preorder_reservation";

    private final JdbcTemplate jdbcTemplate;
    private volatile Boolean preorderItemTableExists;
    private volatile Boolean preorderReservationTableExists;

    public PreorderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listActiveItems(long userId, int limit) {
        if (!hasPreorderItemTable()) {
            return List.of();
        }

        return jdbcTemplate.queryForList(
            "SELECT p.preorder_id, p.material_id, p.seller_id, p.sku_id, "
                + "COALESCE(p.title_override, m.title, m.label, '출간 예정 도서') AS title_ko, "
                + "p.subtitle, p.summary, p.preorder_price, p.list_price, p.discount_rate, "
                + "p.preorder_start_at, p.preorder_end_at, p.release_at, "
                + "p.reservation_limit, p.badge, p.cta_label, p.sort_order, "
                + "m.publisher AS publisher_name, m.issued_year, "
                + "(SELECT COALESCE(a.pref_label, a.label, a.name) "
                + " FROM material_agent ma "
                + " JOIN agent a ON a.agent_id = ma.agent_id "
                + " WHERE ma.material_id = p.material_id "
                + " ORDER BY CASE WHEN ma.role = 'CREATOR' THEN 0 ELSE 1 END, a.pref_label, a.label, a.name "
                + " LIMIT 1) AS author_name, "
                + "COALESCE(rs.total_reserved, 0) AS reserved_count, "
                + "CASE WHEN ur.reservation_id IS NULL THEN 0 ELSE 1 END AS reserved_by_me, "
                + "COALESCE(ur.qty, 0) AS reserved_qty "
                + "FROM preorder_item p "
                + "LEFT JOIN material m ON m.material_id = p.material_id "
                + "LEFT JOIN ("
                + "  SELECT preorder_id, SUM(qty) AS total_reserved "
                + "  FROM preorder_reservation "
                + "  WHERE status = 'RESERVED' "
                + "  GROUP BY preorder_id"
                + ") rs ON rs.preorder_id = p.preorder_id "
                + "LEFT JOIN preorder_reservation ur "
                + "  ON ur.preorder_id = p.preorder_id "
                + " AND ur.user_id = ? "
                + " AND ur.status = 'RESERVED' "
                + "WHERE p.is_active = 1 "
                + "AND p.preorder_start_at <= CURRENT_TIMESTAMP "
                + "AND p.preorder_end_at >= CURRENT_TIMESTAMP "
                + "ORDER BY p.sort_order ASC, p.preorder_id ASC "
                + "LIMIT ?",
            userId,
            limit
        );
    }

    public long countActiveItems() {
        if (!hasPreorderItemTable()) {
            return 0L;
        }
        Long value = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM preorder_item "
                + "WHERE is_active = 1 "
                + "AND preorder_start_at <= CURRENT_TIMESTAMP "
                + "AND preorder_end_at >= CURRENT_TIMESTAMP",
            Long.class
        );
        return value == null ? 0L : value;
    }

    public Map<String, Object> findActiveItemById(long preorderId) {
        if (!hasPreorderItemTable()) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT preorder_id, material_id, seller_id, sku_id, preorder_price, list_price, discount_rate, "
                + "preorder_start_at, preorder_end_at, release_at, reservation_limit, badge, cta_label, is_active "
                + "FROM preorder_item "
                + "WHERE preorder_id = ? "
                + "AND is_active = 1 "
                + "AND preorder_start_at <= CURRENT_TIMESTAMP "
                + "AND preorder_end_at >= CURRENT_TIMESTAMP "
                + "LIMIT 1",
            preorderId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findUserReservation(long preorderId, long userId) {
        if (!hasPreorderReservationTable()) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT reservation_id, preorder_id, user_id, qty, status, reserved_price, order_id, note, created_at, updated_at "
                + "FROM preorder_reservation "
                + "WHERE preorder_id = ? AND user_id = ? "
                + "LIMIT 1",
            preorderId,
            userId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public int countReservedQty(long preorderId) {
        if (!hasPreorderReservationTable()) {
            return 0;
        }
        Integer value = jdbcTemplate.queryForObject(
            "SELECT COALESCE(SUM(qty), 0) FROM preorder_reservation "
                + "WHERE preorder_id = ? AND status = 'RESERVED'",
            Integer.class,
            preorderId
        );
        return value == null ? 0 : value;
    }

    public long insertReservation(long preorderId, long userId, int qty, int reservedPrice, String note) {
        jdbcTemplate.update(
            "INSERT INTO preorder_reservation (preorder_id, user_id, qty, status, reserved_price, note) "
                + "VALUES (?, ?, ?, 'RESERVED', ?, ?)",
            preorderId,
            userId,
            qty,
            reservedPrice,
            note
        );
        Long reservationId = jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
        return reservationId == null ? 0L : reservationId;
    }

    public void updateReservation(long reservationId, int qty, int reservedPrice, String note) {
        jdbcTemplate.update(
            "UPDATE preorder_reservation "
                + "SET qty = ?, status = 'RESERVED', reserved_price = ?, note = ?, order_id = NULL "
                + "WHERE reservation_id = ?",
            qty,
            reservedPrice,
            note,
            reservationId
        );
    }

    private boolean hasPreorderItemTable() {
        Boolean cached = preorderItemTableExists;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (preorderItemTableExists != null) {
                return preorderItemTableExists;
            }
            preorderItemTableExists = tableExists(TABLE_PREORDER_ITEM);
            return preorderItemTableExists;
        }
    }

    private boolean hasPreorderReservationTable() {
        Boolean cached = preorderReservationTableExists;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (preorderReservationTableExists != null) {
                return preorderReservationTableExists;
            }
            preorderReservationTableExists = tableExists(TABLE_PREORDER_RESERVATION);
            return preorderReservationTableExists;
        }
    }

    private boolean tableExists(String tableName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.tables "
                    + "WHERE table_schema = DATABASE() AND table_name = ?",
                Integer.class,
                tableName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }
}
