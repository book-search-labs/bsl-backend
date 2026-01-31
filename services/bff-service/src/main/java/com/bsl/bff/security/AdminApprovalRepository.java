package com.bsl.bff.security;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AdminApprovalRepository {
    private final JdbcTemplate jdbcTemplate;

    public AdminApprovalRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Map<String, Object> findApproval(long approvalId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT approval_id, requested_by_admin_id, action, resource, status, reason, approved_by_admin_id, "
                + "requested_at, approved_at, expires_at FROM admin_action_approval WHERE approval_id = ?",
            approvalId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void markUsed(long approvalId) {
        jdbcTemplate.update(
            "UPDATE admin_action_approval SET status = 'USED', approved_at = CURRENT_TIMESTAMP WHERE approval_id = ?",
            approvalId
        );
    }
}
