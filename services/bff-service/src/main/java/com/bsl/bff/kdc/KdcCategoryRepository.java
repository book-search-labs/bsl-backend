package com.bsl.bff.kdc;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class KdcCategoryRepository {
    private final JdbcTemplate jdbcTemplate;

    public KdcCategoryRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<KdcCategoryRow> listAll() {
        String sql = "SELECT id, code, name, parent_id, depth FROM kdc_node ORDER BY depth ASC, code ASC";
        return jdbcTemplate.query(sql, rowMapper());
    }

    private RowMapper<KdcCategoryRow> rowMapper() {
        return (rs, rowNum) -> new KdcCategoryRow(
            rs.getLong("id"),
            rs.getString("code"),
            rs.getString("name"),
            rs.getObject("parent_id") == null ? null : rs.getLong("parent_id"),
            rs.getInt("depth")
        );
    }

    public record KdcCategoryRow(Long id, String code, String name, Long parentId, Integer depth) {
    }
}
