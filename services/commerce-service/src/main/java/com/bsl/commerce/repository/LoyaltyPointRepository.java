package com.bsl.commerce.repository;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LoyaltyPointRepository {
    private static final String TABLE_ACCOUNT = "loyalty_point_account";
    private static final String TABLE_LEDGER = "loyalty_point_ledger";

    private final JdbcTemplate jdbcTemplate;
    private volatile Boolean accountTableExists;
    private volatile Boolean ledgerTableExists;

    public LoyaltyPointRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void ensureAccount(long userId) {
        if (!hasAccountTable()) {
            return;
        }
        jdbcTemplate.update(
            "INSERT IGNORE INTO loyalty_point_account (user_id, balance) VALUES (?, 0)",
            userId
        );
    }

    public int lockBalance(long userId) {
        if (!hasAccountTable()) {
            return 0;
        }
        ensureAccount(userId);
        Integer value = jdbcTemplate.queryForObject(
            "SELECT balance FROM loyalty_point_account WHERE user_id = ? FOR UPDATE",
            Integer.class,
            userId
        );
        return value == null ? 0 : value;
    }

    public int getBalance(long userId) {
        if (!hasAccountTable()) {
            return 0;
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT balance FROM loyalty_point_account WHERE user_id = ?",
            userId
        );
        if (rows.isEmpty()) {
            return 0;
        }
        Object value = rows.get(0).get("balance");
        if (value instanceof Number number) {
            return number.intValue();
        }
        return 0;
    }

    public boolean existsOrderLedger(long orderId, String type) {
        if (!hasLedgerTable()) {
            return false;
        }
        Integer value = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM loyalty_point_ledger WHERE order_id = ? AND type = ?",
            Integer.class,
            orderId,
            type
        );
        return value != null && value > 0;
    }

    public void updateBalance(long userId, int balance) {
        if (!hasAccountTable()) {
            return;
        }
        jdbcTemplate.update(
            "UPDATE loyalty_point_account SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            balance,
            userId
        );
    }

    public void insertLedger(long userId, Long orderId, String type, int delta, int balanceAfter, String reason) {
        if (!hasLedgerTable()) {
            return;
        }
        jdbcTemplate.update(
            "INSERT INTO loyalty_point_ledger (user_id, order_id, type, delta, balance_after, reason) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
            userId,
            orderId,
            type,
            delta,
            balanceAfter,
            reason
        );
    }

    private boolean hasAccountTable() {
        Boolean cached = accountTableExists;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (accountTableExists != null) {
                return accountTableExists;
            }
            accountTableExists = hasTable(TABLE_ACCOUNT);
            return accountTableExists;
        }
    }

    private boolean hasLedgerTable() {
        Boolean cached = ledgerTableExists;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (ledgerTableExists != null) {
                return ledgerTableExists;
            }
            ledgerTableExists = hasTable(TABLE_LEDGER);
            return ledgerTableExists;
        }
    }

    private boolean hasTable(String tableName) {
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
