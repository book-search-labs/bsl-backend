package com.bsl.commerce.repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class SupportTicketRepository {
    private final JdbcTemplate jdbcTemplate;

    public SupportTicketRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public long insertTicket(
        String ticketNo,
        long userId,
        Long orderId,
        String category,
        String severity,
        String status,
        String summary,
        String detailJson,
        String errorCode,
        String chatSessionId,
        String chatRequestId,
        Timestamp expectedResponseAt
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO support_ticket (ticket_no, user_id, order_id, category, severity, status, summary, detail_json, "
                    + "error_code, chat_session_id, chat_request_id, expected_response_at) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, ticketNo);
            ps.setLong(2, userId);
            if (orderId == null) {
                ps.setObject(3, null);
            } else {
                ps.setLong(3, orderId);
            }
            ps.setString(4, category);
            ps.setString(5, severity);
            ps.setString(6, status);
            ps.setString(7, summary);
            ps.setString(8, detailJson);
            ps.setString(9, errorCode);
            ps.setString(10, chatSessionId);
            ps.setString(11, chatRequestId);
            ps.setTimestamp(12, expectedResponseAt);
            return ps;
        }, keyHolder);

        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public Map<String, Object> findTicketById(long ticketId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT ticket_id, ticket_no, user_id, order_id, category, severity, status, summary, detail_json, "
                + "error_code, chat_session_id, chat_request_id, expected_response_at, resolved_at, created_at, updated_at "
                + "FROM support_ticket WHERE ticket_id = ?",
            ticketId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findTicketByNo(String ticketNo) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT ticket_id, ticket_no, user_id, order_id, category, severity, status, summary, detail_json, "
                + "error_code, chat_session_id, chat_request_id, expected_response_at, resolved_at, created_at, updated_at "
                + "FROM support_ticket WHERE ticket_no = ?",
            ticketNo
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listTicketsByUser(long userId, int limit) {
        return jdbcTemplate.queryForList(
            "SELECT ticket_id, ticket_no, user_id, order_id, category, severity, status, summary, detail_json, "
                + "error_code, chat_session_id, chat_request_id, expected_response_at, resolved_at, created_at, updated_at "
                + "FROM support_ticket WHERE user_id = ? ORDER BY ticket_id DESC LIMIT ?",
            userId,
            limit
        );
    }

    public void updateStatus(long ticketId, String status, Timestamp resolvedAt) {
        jdbcTemplate.update(
            "UPDATE support_ticket SET status = ?, resolved_at = ?, updated_at = CURRENT_TIMESTAMP WHERE ticket_id = ?",
            status,
            resolvedAt,
            ticketId
        );
    }

    public void insertTicketEvent(
        long ticketId,
        String eventType,
        String fromStatus,
        String toStatus,
        String note,
        String payloadJson
    ) {
        jdbcTemplate.update(
            "INSERT INTO support_ticket_event (ticket_id, event_type, from_status, to_status, note, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
            ticketId,
            eventType,
            fromStatus,
            toStatus,
            note,
            payloadJson
        );
    }

    public List<Map<String, Object>> listTicketEvents(long ticketId) {
        return jdbcTemplate.queryForList(
            "SELECT ticket_event_id, ticket_id, event_type, from_status, to_status, note, payload_json, created_at "
                + "FROM support_ticket_event WHERE ticket_id = ? ORDER BY ticket_event_id",
            ticketId
        );
    }
}
