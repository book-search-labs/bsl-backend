package com.bsl.bff.authority;

import com.bsl.bff.authority.dto.AgentAliasDto;
import com.bsl.bff.authority.dto.AuthorityMergeGroupDto;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class AuthorityRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public AuthorityRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public List<AuthorityMergeGroupDto> listMergeGroups(int limit, String status) {
        StringBuilder sql = new StringBuilder(
            "SELECT group_id, status, rule_version, group_key, master_material_id, members_json, created_at, updated_at "
                + "FROM material_merge_group"
        );
        Object[] params;
        if (status != null && !status.isBlank()) {
            sql.append(" WHERE status = ? ORDER BY updated_at DESC LIMIT ?");
            params = new Object[] { status, limit };
        } else {
            sql.append(" ORDER BY updated_at DESC LIMIT ?");
            params = new Object[] { limit };
        }
        return jdbcTemplate.query(sql.toString(), params, mergeGroupMapper());
    }

    public Optional<AuthorityMergeGroupDto> resolveMergeGroup(long groupId, String masterMaterialId, String status) {
        String resolvedStatus = status == null || status.isBlank() ? "RESOLVED" : status;
        jdbcTemplate.update(
            "UPDATE material_merge_group SET master_material_id = ?, status = ? WHERE group_id = ?",
            masterMaterialId,
            resolvedStatus,
            groupId
        );
        List<AuthorityMergeGroupDto> rows = jdbcTemplate.query(
            "SELECT group_id, status, rule_version, group_key, master_material_id, members_json, created_at, updated_at "
                + "FROM material_merge_group WHERE group_id = ?",
            new Object[] { groupId },
            mergeGroupMapper()
        );
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public List<AgentAliasDto> listAgentAliases(int limit, String query, String status) {
        StringBuilder sql = new StringBuilder(
            "SELECT alias_id, alias_name, canonical_name, canonical_agent_id, status, created_at, updated_at "
                + "FROM agent_alias"
        );
        boolean hasQuery = query != null && !query.isBlank();
        boolean hasStatus = status != null && !status.isBlank();
        if (hasQuery || hasStatus) {
            sql.append(" WHERE ");
        }
        if (hasQuery) {
            sql.append("alias_name LIKE ? ");
        }
        if (hasQuery && hasStatus) {
            sql.append("AND status = ? ");
        } else if (hasStatus) {
            sql.append("status = ? ");
        }
        sql.append("ORDER BY updated_at DESC LIMIT ?");

        Object[] params;
        if (hasQuery && hasStatus) {
            params = new Object[] { "%" + query + "%", status, limit };
        } else if (hasQuery) {
            params = new Object[] { "%" + query + "%", limit };
        } else if (hasStatus) {
            params = new Object[] { status, limit };
        } else {
            params = new Object[] { limit };
        }
        return jdbcTemplate.query(sql.toString(), params, agentAliasMapper());
    }

    public Optional<AgentAliasDto> upsertAgentAlias(
        String aliasName,
        String canonicalName,
        String canonicalAgentId,
        String status
    ) {
        String resolvedStatus = status == null || status.isBlank() ? "ACTIVE" : status;
        jdbcTemplate.update(
            "INSERT INTO agent_alias (alias_name, canonical_name, canonical_agent_id, status) VALUES (?, ?, ?, ?) "
                + "ON DUPLICATE KEY UPDATE canonical_name = VALUES(canonical_name), "
                + "canonical_agent_id = VALUES(canonical_agent_id), status = VALUES(status)",
            aliasName,
            canonicalName,
            canonicalAgentId,
            resolvedStatus
        );
        List<AgentAliasDto> rows = jdbcTemplate.query(
            "SELECT alias_id, alias_name, canonical_name, canonical_agent_id, status, created_at, updated_at "
                + "FROM agent_alias WHERE alias_name = ?",
            new Object[] { aliasName },
            agentAliasMapper()
        );
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public Optional<AgentAliasDto> deleteAgentAlias(long aliasId) {
        jdbcTemplate.update(
            "UPDATE agent_alias SET status = 'DELETED' WHERE alias_id = ?",
            aliasId
        );
        List<AgentAliasDto> rows = jdbcTemplate.query(
            "SELECT alias_id, alias_name, canonical_name, canonical_agent_id, status, created_at, updated_at "
                + "FROM agent_alias WHERE alias_id = ?",
            new Object[] { aliasId },
            agentAliasMapper()
        );
        return rows.isEmpty() ? Optional.empty() : Optional.of(rows.get(0));
    }

    public java.util.Map<String, String> resolveAliases(List<String> names) {
        if (names == null || names.isEmpty()) {
            return java.util.Collections.emptyMap();
        }
        StringBuilder placeholders = new StringBuilder();
        for (int i = 0; i < names.size(); i++) {
            if (i > 0) {
                placeholders.append(",");
            }
            placeholders.append("?");
        }
        String sql = "SELECT alias_name, canonical_name FROM agent_alias "
            + "WHERE status = 'ACTIVE' AND alias_name IN (" + placeholders + ")";
        List<java.util.Map<String, Object>> rows = jdbcTemplate.queryForList(sql, names.toArray());
        java.util.Map<String, String> mapping = new java.util.HashMap<>();
        for (java.util.Map<String, Object> row : rows) {
            Object alias = row.get("alias_name");
            Object canonical = row.get("canonical_name");
            if (alias != null && canonical != null) {
                mapping.put(String.valueOf(alias), String.valueOf(canonical));
            }
        }
        return mapping;
    }

    private RowMapper<AuthorityMergeGroupDto> mergeGroupMapper() {
        return (rs, rowNum) -> {
            AuthorityMergeGroupDto dto = new AuthorityMergeGroupDto();
            dto.setGroupId(rs.getLong("group_id"));
            dto.setStatus(rs.getString("status"));
            dto.setRuleVersion(rs.getString("rule_version"));
            dto.setGroupKey(rs.getString("group_key"));
            dto.setMasterMaterialId(rs.getString("master_material_id"));
            dto.setMembers(readJson(rs.getString("members_json")));
            dto.setCreatedAt(readInstant(rs, "created_at"));
            dto.setUpdatedAt(readInstant(rs, "updated_at"));
            return dto;
        };
    }

    private RowMapper<AgentAliasDto> agentAliasMapper() {
        return (rs, rowNum) -> {
            AgentAliasDto dto = new AgentAliasDto();
            dto.setAliasId(rs.getLong("alias_id"));
            dto.setAliasName(rs.getString("alias_name"));
            dto.setCanonicalName(rs.getString("canonical_name"));
            dto.setCanonicalAgentId(rs.getString("canonical_agent_id"));
            dto.setStatus(rs.getString("status"));
            dto.setCreatedAt(readInstant(rs, "created_at"));
            dto.setUpdatedAt(readInstant(rs, "updated_at"));
            return dto;
        };
    }

    private Instant readInstant(ResultSet rs, String column) throws SQLException {
        Timestamp ts = rs.getTimestamp(column);
        return ts == null ? null : ts.toInstant();
    }

    private JsonNode readJson(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return objectMapper.readTree(value);
        } catch (Exception ex) {
            return null;
        }
    }
}
