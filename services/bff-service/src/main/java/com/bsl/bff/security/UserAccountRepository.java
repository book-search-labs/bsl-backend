package com.bsl.bff.security;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class UserAccountRepository {
    private static final RowMapper<UserAccount> ROW_MAPPER = new RowMapper<>() {
        @Override
        public UserAccount mapRow(ResultSet rs, int rowNum) throws SQLException {
            return new UserAccount(
                rs.getLong("user_id"),
                rs.getString("email"),
                rs.getString("password_hash"),
                rs.getString("name"),
                rs.getString("phone")
            );
        }
    };

    private final JdbcTemplate jdbcTemplate;

    public UserAccountRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<UserAccount> findActiveByEmail(String email) {
        if (email == null || email.isBlank()) {
            return Optional.empty();
        }
        return jdbcTemplate.query(
            "SELECT user_id, email, password_hash, name, phone "
                + "FROM user_account WHERE email = ? AND status = 'ACTIVE' AND deleted_at IS NULL LIMIT 1",
            ROW_MAPPER,
            email.trim().toLowerCase()
        ).stream().findFirst();
    }

    public Optional<UserAccount> findActiveById(long userId) {
        if (userId <= 0) {
            return Optional.empty();
        }
        return jdbcTemplate.query(
            "SELECT user_id, email, password_hash, name, phone "
                + "FROM user_account WHERE user_id = ? AND status = 'ACTIVE' AND deleted_at IS NULL LIMIT 1",
            ROW_MAPPER,
            userId
        ).stream().findFirst();
    }

    public void updateLastLogin(long userId) {
        if (userId <= 0) {
            return;
        }
        jdbcTemplate.update("UPDATE user_account SET last_login_at = CURRENT_TIMESTAMP WHERE user_id = ?", userId);
    }

    public record UserAccount(
        long userId,
        String email,
        String passwordHash,
        String name,
        String phone
    ) {
    }
}
