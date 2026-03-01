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
public class SellerRepository {
    private final JdbcTemplate jdbcTemplate;

    public SellerRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listSellers(int limit) {
        return jdbcTemplate.queryForList(
            "SELECT seller_id, name, status, policy_json, created_at FROM seller ORDER BY seller_id DESC LIMIT ?",
            limit
        );
    }

    public Long findActiveSellerId() {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT seller_id FROM seller WHERE status = 'ACTIVE' ORDER BY seller_id ASC LIMIT 1"
        );
        if (rows.isEmpty()) {
            return null;
        }
        Object raw = rows.get(0).get("seller_id");
        if (raw instanceof Number number) {
            return number.longValue();
        }
        return null;
    }

    public Map<String, Object> findSeller(long sellerId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT seller_id, name, status, policy_json, created_at FROM seller WHERE seller_id = ?",
            sellerId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertSeller(String name, String status, String policyJson) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO seller (name, status, policy_json) VALUES (?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, name);
            ps.setString(2, status);
            ps.setString(3, policyJson);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void updateSeller(long sellerId, String name, String status, String policyJson) {
        jdbcTemplate.update(
            "UPDATE seller SET name = ?, status = ?, policy_json = ? WHERE seller_id = ?",
            name,
            status,
            policyJson,
            sellerId
        );
    }
}
