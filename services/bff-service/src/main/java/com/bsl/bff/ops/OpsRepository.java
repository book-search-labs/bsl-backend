package com.bsl.bff.ops;

import com.bsl.bff.ops.dto.JobRunDto;
import com.bsl.bff.ops.dto.OpsTaskDto;
import com.bsl.bff.ops.dto.ReindexJobDto;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class OpsRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public OpsRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public List<JobRunDto> fetchJobRuns(int limit, String status) {
        StringBuilder sql = new StringBuilder(
            "SELECT job_run_id, job_type, status, params_json, started_at, finished_at, error_message "
                + "FROM job_run"
        );
        List<Object> params = new ArrayList<>();
        appendFilter(sql, params, "status", status);
        sql.append(" ORDER BY started_at DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.query(sql.toString(), jobRunMapper(), params.toArray());
    }

    public Optional<JobRunDto> findJobRun(long jobRunId) {
        List<JobRunDto> rows = jdbcTemplate.query(
            "SELECT job_run_id, job_type, status, params_json, started_at, finished_at, error_message "
                + "FROM job_run WHERE job_run_id=?",
            jobRunMapper(),
            jobRunId
        );
        if (rows.isEmpty()) {
            return Optional.empty();
        }
        return Optional.of(rows.get(0));
    }

    public JobRunDto insertJobRunRetry(JobRunDto source) {
        String paramsJson = toJson(source.getParams());
        Timestamp now = Timestamp.from(Instant.now());
        KeyHolder keyHolder = new GeneratedKeyHolder();

        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO job_run (job_type, status, params_json, started_at) VALUES (?, ?, ?, ?)",
                PreparedStatement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, source.getJobType());
            ps.setString(2, "RUNNING");
            if (paramsJson == null) {
                ps.setNull(3, Types.LONGVARCHAR);
            } else {
                ps.setString(3, paramsJson);
            }
            ps.setTimestamp(4, now);
            return ps;
        }, keyHolder);

        Number key = keyHolder.getKey();
        if (key != null) {
            Optional<JobRunDto> inserted = findJobRun(key.longValue());
            if (inserted.isPresent()) {
                return inserted.get();
            }
        }

        JobRunDto fallback = new JobRunDto();
        fallback.setJobRunId(key == null ? null : key.longValue());
        fallback.setJobType(source.getJobType());
        fallback.setStatus("RUNNING");
        fallback.setParams(source.getParams());
        fallback.setStartedAt(now.toInstant());
        return fallback;
    }

    public List<ReindexJobDto> fetchReindexJobs(int limit, String status, String logicalName) {
        StringBuilder sql = new StringBuilder(
            "SELECT reindex_job_id, logical_name, from_physical, to_physical, status, params_json, "
                + "progress_json, error_json, error_message, started_at, finished_at, created_at, updated_at, paused_at "
                + "FROM reindex_job"
        );
        List<Object> params = new ArrayList<>();
        appendFilter(sql, params, "status", status);
        appendFilter(sql, params, "logical_name", logicalName);
        sql.append(" ORDER BY updated_at DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.query(sql.toString(), reindexJobMapper(), params.toArray());
    }

    public List<OpsTaskDto> fetchOpsTasks(int limit, String status, String taskType) {
        StringBuilder sql = new StringBuilder(
            "SELECT task_id, task_type, status, payload_json, assigned_admin_id, created_at, updated_at "
                + "FROM ops_task"
        );
        List<Object> params = new ArrayList<>();
        appendFilter(sql, params, "status", status);
        appendFilter(sql, params, "task_type", taskType);
        sql.append(" ORDER BY created_at DESC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.query(sql.toString(), opsTaskMapper(), params.toArray());
    }

    private void appendFilter(StringBuilder sql, List<Object> params, String column, String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        if (params.isEmpty()) {
            sql.append(" WHERE ");
        } else {
            sql.append(" AND ");
        }
        sql.append(column).append("=?");
        params.add(value.trim());
    }

    private RowMapper<JobRunDto> jobRunMapper() {
        return (rs, rowNum) -> {
            JobRunDto dto = new JobRunDto();
            dto.setJobRunId(rs.getLong("job_run_id"));
            dto.setJobType(rs.getString("job_type"));
            dto.setStatus(rs.getString("status"));
            dto.setParams(parseJson(rs.getString("params_json")));
            dto.setErrorMessage(rs.getString("error_message"));
            dto.setStartedAt(toInstant(rs.getTimestamp("started_at")));
            dto.setFinishedAt(toInstant(rs.getTimestamp("finished_at")));
            return dto;
        };
    }

    private RowMapper<ReindexJobDto> reindexJobMapper() {
        return (rs, rowNum) -> {
            ReindexJobDto dto = new ReindexJobDto();
            dto.setReindexJobId(rs.getLong("reindex_job_id"));
            dto.setLogicalName(rs.getString("logical_name"));
            dto.setFromPhysical(rs.getString("from_physical"));
            dto.setToPhysical(rs.getString("to_physical"));
            dto.setStatus(rs.getString("status"));
            dto.setParams(parseJson(rs.getString("params_json")));
            dto.setProgress(parseJson(rs.getString("progress_json")));
            dto.setError(parseJson(rs.getString("error_json")));
            dto.setErrorMessage(rs.getString("error_message"));
            dto.setStartedAt(toInstant(rs.getTimestamp("started_at")));
            dto.setFinishedAt(toInstant(rs.getTimestamp("finished_at")));
            dto.setCreatedAt(toInstant(rs.getTimestamp("created_at")));
            dto.setUpdatedAt(toInstant(rs.getTimestamp("updated_at")));
            dto.setPausedAt(toInstant(rs.getTimestamp("paused_at")));
            return dto;
        };
    }

    private RowMapper<OpsTaskDto> opsTaskMapper() {
        return (rs, rowNum) -> {
            OpsTaskDto dto = new OpsTaskDto();
            dto.setTaskId(rs.getLong("task_id"));
            dto.setTaskType(rs.getString("task_type"));
            dto.setStatus(rs.getString("status"));
            dto.setPayload(parseJson(rs.getString("payload_json")));
            long assigned = rs.getLong("assigned_admin_id");
            if (rs.wasNull()) {
                dto.setAssignedAdminId(null);
            } else {
                dto.setAssignedAdminId(assigned);
            }
            dto.setCreatedAt(toInstant(rs.getTimestamp("created_at")));
            dto.setUpdatedAt(toInstant(rs.getTimestamp("updated_at")));
            return dto;
        };
    }

    private Object parseJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return objectMapper.readValue(raw, Object.class);
        } catch (JsonProcessingException ex) {
            return null;
        }
    }

    private String toJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            return null;
        }
    }

    private Instant toInstant(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toInstant();
    }
}
