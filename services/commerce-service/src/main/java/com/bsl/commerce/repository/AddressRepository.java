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
public class AddressRepository {
    private final JdbcTemplate jdbcTemplate;

    public AddressRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listAddresses(long userId) {
        return jdbcTemplate.queryForList(
            "SELECT address_id, user_id, name, phone, zip, addr1, addr2, is_default, created_at "
                + "FROM user_address WHERE user_id = ? ORDER BY is_default DESC, address_id DESC",
            userId
        );
    }

    public Map<String, Object> findAddress(long addressId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT address_id, user_id, name, phone, zip, addr1, addr2, is_default, created_at "
                + "FROM user_address WHERE address_id = ?",
            addressId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertAddress(
        long userId,
        String name,
        String phone,
        String zip,
        String addr1,
        String addr2,
        boolean isDefault
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO user_address (user_id, name, phone, zip, addr1, addr2, is_default) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, userId);
            ps.setString(2, name);
            ps.setString(3, phone);
            ps.setString(4, zip);
            ps.setString(5, addr1);
            ps.setString(6, addr2);
            ps.setBoolean(7, isDefault);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void clearDefault(long userId) {
        jdbcTemplate.update("UPDATE user_address SET is_default = 0 WHERE user_id = ?", userId);
    }

    public void setDefault(long addressId) {
        jdbcTemplate.update("UPDATE user_address SET is_default = 1 WHERE address_id = ?", addressId);
    }
}
