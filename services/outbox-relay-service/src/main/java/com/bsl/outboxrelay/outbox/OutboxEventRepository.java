package com.bsl.outboxrelay.outbox;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxEventRepository {
    private final JdbcTemplate jdbcTemplate;

    public OutboxEventRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OutboxEvent> fetchNewEvents(int limit) {
        return jdbcTemplate.query(
            "SELECT event_id, event_type, aggregate_type, aggregate_id, dedup_key, payload_json, created_at "
                + "FROM outbox_event WHERE status='NEW' ORDER BY event_id ASC LIMIT ?",
            new OutboxRowMapper(),
            limit
        );
    }

    public void markSent(List<Long> ids) {
        if (ids.isEmpty()) {
            return;
        }
        jdbcTemplate.batchUpdate(
            "UPDATE outbox_event SET status='SENT', sent_at=NOW() WHERE event_id=?",
            ids,
            ids.size(),
            (ps, argument) -> ps.setLong(1, argument)
        );
    }

    public void markFailed(List<Long> ids) {
        if (ids.isEmpty()) {
            return;
        }
        jdbcTemplate.batchUpdate(
            "UPDATE outbox_event SET status='FAILED' WHERE event_id=?",
            ids,
            ids.size(),
            (ps, argument) -> ps.setLong(1, argument)
        );
    }

    public long countByStatus(String status) {
        Long value = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM outbox_event WHERE status=?",
            Long.class,
            status
        );
        return value == null ? 0L : value;
    }

    public Instant minCreatedAtForStatus(String status) {
        Timestamp timestamp = jdbcTemplate.queryForObject(
            "SELECT MIN(created_at) FROM outbox_event WHERE status=?",
            Timestamp.class,
            status
        );
        return timestamp == null ? null : timestamp.toInstant();
    }

    private static class OutboxRowMapper implements RowMapper<OutboxEvent> {
        @Override
        public OutboxEvent mapRow(ResultSet rs, int rowNum) throws SQLException {
            long eventId = rs.getLong("event_id");
            String eventType = rs.getString("event_type");
            String aggregateType = rs.getString("aggregate_type");
            String aggregateId = rs.getString("aggregate_id");
            String dedupKey = rs.getString("dedup_key");
            String payloadJson = rs.getString("payload_json");
            Timestamp createdAt = rs.getTimestamp("created_at");
            return new OutboxEvent(
                eventId,
                eventType,
                aggregateType,
                aggregateId,
                dedupKey,
                payloadJson,
                createdAt == null ? Instant.EPOCH : createdAt.toInstant()
            );
        }
    }
}
