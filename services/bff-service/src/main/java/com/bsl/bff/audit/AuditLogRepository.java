package com.bsl.bff.audit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditLogRepository {
    private final JdbcTemplate jdbcTemplate;

    public AuditLogRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(
        long adminId,
        String action,
        String resourceType,
        String resourceId,
        String beforeJson,
        String afterJson,
        String requestId,
        String traceId,
        String ip,
        String userAgent
    ) {
        jdbcTemplate.update(
            "INSERT INTO audit_log (actor_admin_id, action, resource_type, resource_id, before_json, after_json, "
                + "request_id, trace_id, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            adminId,
            action,
            resourceType,
            resourceId,
            beforeJson,
            afterJson,
            requestId,
            traceId,
            ip,
            userAgent
        );
    }
}
