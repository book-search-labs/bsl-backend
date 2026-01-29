package com.bsl.bff.outbox;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxEventRepository {
    private final JdbcTemplate jdbcTemplate;

    public OutboxEventRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(OutboxEvent event) {
        jdbcTemplate.update(
            "INSERT INTO outbox_event (event_type, aggregate_type, aggregate_id, dedup_key, payload_json, status) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
            event.getEventType(),
            event.getAggregateType(),
            event.getAggregateId(),
            event.getDedupKey(),
            event.getPayloadJson(),
            event.getStatus()
        );
    }
}
