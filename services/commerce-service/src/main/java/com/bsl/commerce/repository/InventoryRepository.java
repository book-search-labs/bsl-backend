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
public class InventoryRepository {
    private final JdbcTemplate jdbcTemplate;

    public InventoryRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findBalance(long skuId, long sellerId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT sku_id, seller_id, on_hand, reserved, available, updated_at FROM inventory_balance "
                + "WHERE sku_id = ? AND seller_id = ?",
            skuId,
            sellerId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findBalanceForUpdate(long skuId, long sellerId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT sku_id, seller_id, on_hand, reserved, available, updated_at FROM inventory_balance "
                + "WHERE sku_id = ? AND seller_id = ? FOR UPDATE",
            skuId,
            sellerId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void insertBalance(long skuId, long sellerId) {
        jdbcTemplate.update(
            "INSERT INTO inventory_balance (sku_id, seller_id, on_hand, reserved) VALUES (?, ?, 0, 0)",
            skuId,
            sellerId
        );
    }

    public void updateBalance(long skuId, long sellerId, int onHand, int reserved) {
        jdbcTemplate.update(
            "UPDATE inventory_balance SET on_hand = ?, reserved = ? WHERE sku_id = ? AND seller_id = ?",
            onHand,
            reserved,
            skuId,
            sellerId
        );
    }

    public Map<String, Object> findLedgerByIdempotencyKey(String idempotencyKey) {
        if (idempotencyKey == null) {
            return null;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT ledger_id, sku_id, seller_id, type, delta, idempotency_key, ref_type, ref_id, note, created_at "
                + "FROM inventory_ledger WHERE idempotency_key = ?",
            idempotencyKey
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertLedger(
        long skuId,
        long sellerId,
        String type,
        int delta,
        String idempotencyKey,
        String refType,
        String refId,
        String note,
        Long adminId
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO inventory_ledger (sku_id, seller_id, type, delta, idempotency_key, ref_type, ref_id, note, "
                    + "created_by_admin_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, skuId);
            ps.setLong(2, sellerId);
            ps.setString(3, type);
            ps.setInt(4, delta);
            ps.setString(5, idempotencyKey);
            ps.setString(6, refType);
            ps.setString(7, refId);
            ps.setString(8, note);
            if (adminId == null) {
                ps.setObject(9, null);
            } else {
                ps.setLong(9, adminId);
            }
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public List<Map<String, Object>> listLedger(long skuId, long sellerId, int limit) {
        return jdbcTemplate.queryForList(
            "SELECT ledger_id, sku_id, seller_id, type, delta, idempotency_key, ref_type, ref_id, note, created_at "
                + "FROM inventory_ledger WHERE sku_id = ? AND seller_id = ? ORDER BY ledger_id DESC LIMIT ?",
            skuId,
            sellerId,
            limit
        );
    }
}
