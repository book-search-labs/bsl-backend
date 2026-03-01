package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class SettlementRepository {
    private final JdbcTemplate jdbcTemplate;

    public SettlementRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findCycleById(long cycleId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT cycle_id, start_date, end_date, status, generated_at, created_at, updated_at "
                + "FROM settlement_cycle WHERE cycle_id = ?",
            cycleId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findCycleByPeriod(LocalDate startDate, LocalDate endDate) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT cycle_id, start_date, end_date, status, generated_at, created_at, updated_at "
                + "FROM settlement_cycle WHERE start_date = ? AND end_date = ?",
            startDate,
            endDate
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listCycles(int limit, String status, LocalDate fromDate, LocalDate toDate) {
        StringBuilder sql = new StringBuilder(
            "SELECT cycle_id, start_date, end_date, status, generated_at, created_at, updated_at "
                + "FROM settlement_cycle WHERE 1=1"
        );
        List<Object> params = new ArrayList<>();
        if (status != null && !status.isBlank()) {
            sql.append(" AND status = ?");
            params.add(status);
        }
        if (fromDate != null) {
            sql.append(" AND end_date >= ?");
            params.add(fromDate);
        }
        if (toDate != null) {
            sql.append(" AND start_date <= ?");
            params.add(toDate);
        }
        sql.append(" ORDER BY cycle_id DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public long insertCycle(LocalDate startDate, LocalDate endDate, String status) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO settlement_cycle (start_date, end_date, status, generated_at) VALUES (?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setObject(1, startDate);
            ps.setObject(2, endDate);
            ps.setString(3, status);
            ps.setTimestamp(4, Timestamp.from(java.time.Instant.now()));
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void updateCycleStatus(long cycleId, String status) {
        jdbcTemplate.update(
            "UPDATE settlement_cycle SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE cycle_id = ?",
            status,
            cycleId
        );
    }

    public boolean insertLine(long cycleId, long sellerId, int grossSales, int totalFees, int netAmount, String status) {
        try {
            jdbcTemplate.update(
                "INSERT INTO settlement_line (cycle_id, seller_id, gross_sales, total_fees, net_amount, status) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                cycleId,
                sellerId,
                grossSales,
                totalFees,
                netAmount,
                status
            );
            return true;
        } catch (DuplicateKeyException ex) {
            return false;
        }
    }

    public List<Map<String, Object>> listLines(long cycleId) {
        return jdbcTemplate.queryForList(
            "SELECT settlement_line_id, cycle_id, seller_id, gross_sales, total_fees, net_amount, status, created_at, updated_at "
                + "FROM settlement_line WHERE cycle_id = ? ORDER BY seller_id",
            cycleId
        );
    }

    public List<Map<String, Object>> listLinesForPayout(long cycleId) {
        return jdbcTemplate.queryForList(
            "SELECT settlement_line_id, cycle_id, seller_id, gross_sales, total_fees, net_amount, status "
                + "FROM settlement_line WHERE cycle_id = ? AND status <> 'PAID' ORDER BY seller_id",
            cycleId
        );
    }

    public boolean insertPayout(long settlementLineId, String status) {
        try {
            jdbcTemplate.update(
                "INSERT INTO payout (settlement_line_id, status) VALUES (?, ?)",
                settlementLineId,
                status
            );
            return true;
        } catch (DuplicateKeyException ex) {
            return false;
        }
    }

    public void updatePayoutStatus(long settlementLineId, String status, String failureReason) {
        jdbcTemplate.update(
            "UPDATE payout SET status = ?, paid_at = CASE WHEN ? = 'PAID' THEN CURRENT_TIMESTAMP ELSE paid_at END, "
                + "failure_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE settlement_line_id = ?",
            status,
            status,
            failureReason,
            settlementLineId
        );
    }

    public void updateLineStatus(long settlementLineId, String status) {
        jdbcTemplate.update(
            "UPDATE settlement_line SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE settlement_line_id = ?",
            status,
            settlementLineId
        );
    }

    public List<Map<String, Object>> listPayoutsByCycle(long cycleId) {
        return jdbcTemplate.queryForList(
            "SELECT p.payout_id, p.settlement_line_id, p.status, p.paid_at, p.failure_reason, p.created_at, p.updated_at "
                + "FROM payout p "
                + "JOIN settlement_line l ON l.settlement_line_id = p.settlement_line_id "
                + "WHERE l.cycle_id = ? ORDER BY p.payout_id",
            cycleId
        );
    }

    public Map<String, Object> findPayoutById(long payoutId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT p.payout_id, p.settlement_line_id, p.status, p.paid_at, p.failure_reason, p.created_at, p.updated_at, "
                + "l.cycle_id, l.net_amount, l.status AS line_status "
                + "FROM payout p "
                + "JOIN settlement_line l ON l.settlement_line_id = p.settlement_line_id "
                + "WHERE p.payout_id = ? LIMIT 1",
            payoutId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listPayouts(int limit, String status) {
        StringBuilder sql = new StringBuilder(
            "SELECT p.payout_id, p.settlement_line_id, p.status, p.paid_at, p.failure_reason, p.created_at, p.updated_at, "
                + "l.cycle_id, l.seller_id, l.net_amount, l.status AS line_status "
                + "FROM payout p "
                + "JOIN settlement_line l ON l.settlement_line_id = p.settlement_line_id "
                + "WHERE 1=1"
        );
        List<Object> params = new ArrayList<>();
        if (status != null && !status.isBlank()) {
            sql.append(" AND p.status = ?");
            params.add(status);
        }
        sql.append(" ORDER BY p.payout_id DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public List<Map<String, Object>> listReconciliationMismatches(int limit, LocalDate fromDate, LocalDate toDate) {
        StringBuilder sql = new StringBuilder(
            "SELECT p.payment_id, p.order_id, p.amount AS payment_amount, p.currency, p.provider, p.created_at, "
                + "COALESCE(SUM(CASE WHEN l.entry_type = 'SALE' THEN l.amount ELSE 0 END), 0) AS sale_amount, "
                + "COALESCE(SUM(CASE WHEN l.entry_type = 'PG_FEE' THEN l.amount ELSE 0 END), 0) AS pg_fee_amount, "
                + "COALESCE(SUM(CASE WHEN l.entry_type = 'PLATFORM_FEE' THEN l.amount ELSE 0 END), 0) AS platform_fee_amount, "
                + "COALESCE(SUM(CASE WHEN l.entry_type = 'REFUND' THEN l.amount ELSE 0 END), 0) AS refund_amount, "
                + "COUNT(l.ledger_entry_id) AS ledger_entry_count "
                + "FROM payment p "
                + "LEFT JOIN ledger_entry l ON l.payment_id = p.payment_id "
                + "WHERE p.status = 'CAPTURED'"
        );
        List<Object> params = new ArrayList<>();
        if (fromDate != null) {
            sql.append(" AND DATE(p.created_at) >= ?");
            params.add(fromDate);
        }
        if (toDate != null) {
            sql.append(" AND DATE(p.created_at) <= ?");
            params.add(toDate);
        }
        sql.append(
            " GROUP BY p.payment_id, p.order_id, p.amount, p.currency, p.provider, p.created_at "
                + "HAVING ledger_entry_count = 0 OR sale_amount <> p.amount "
                + "ORDER BY p.payment_id DESC LIMIT ?"
        );
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public int countUnpaidLines(long cycleId) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM settlement_line WHERE cycle_id = ? AND status <> 'PAID'",
            Integer.class,
            cycleId
        );
        return count == null ? 0 : count;
    }

    public int countLinesByStatus(long cycleId, String status) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM settlement_line WHERE cycle_id = ? AND status = ?",
            Integer.class,
            cycleId,
            status
        );
        return count == null ? 0 : count;
    }
}
