package com.bsl.commerce.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LedgerRepository {
    private final JdbcTemplate jdbcTemplate;

    public LedgerRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean insertEntry(
        long sellerId,
        long orderId,
        Long paymentId,
        String entryType,
        int amount,
        String currency,
        Instant occurredAt,
        String referenceId
    ) {
        try {
            jdbcTemplate.update(
                "INSERT INTO ledger_entry (seller_id, order_id, payment_id, entry_type, amount, currency, occurred_at, reference_id) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                sellerId,
                orderId,
                paymentId,
                entryType,
                amount,
                currency,
                Timestamp.from(occurredAt == null ? Instant.now() : occurredAt),
                referenceId
            );
            return true;
        } catch (DuplicateKeyException ex) {
            return false;
        }
    }

    public List<Map<String, Object>> aggregateSellerLines(LocalDate startDate, LocalDate endDateInclusive) {
        LocalDateTime from = startDate.atStartOfDay();
        LocalDateTime toExclusive = endDateInclusive.plusDays(1).atStartOfDay();
        return jdbcTemplate.queryForList(
            "SELECT seller_id, "
                + "SUM(CASE WHEN entry_type = 'SALE' THEN amount ELSE 0 END) AS gross_sales, "
                + "SUM(CASE WHEN entry_type IN ('PG_FEE', 'PLATFORM_FEE', 'REFUND') THEN amount ELSE 0 END) AS total_fees "
                + "FROM ledger_entry "
                + "WHERE occurred_at >= ? AND occurred_at < ? "
                + "GROUP BY seller_id",
            Timestamp.valueOf(from),
            Timestamp.valueOf(toExclusive)
        );
    }
}
