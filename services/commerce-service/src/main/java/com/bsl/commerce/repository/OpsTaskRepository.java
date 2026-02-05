package com.bsl.commerce.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OpsTaskRepository {
    private final JdbcTemplate jdbcTemplate;

    public OpsTaskRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insertTask(String taskType, String status, String payloadJson) {
        jdbcTemplate.update(
            "INSERT INTO ops_task (task_type, status, payload_json) VALUES (?, ?, ?)",
            taskType,
            status,
            payloadJson
        );
    }
}
