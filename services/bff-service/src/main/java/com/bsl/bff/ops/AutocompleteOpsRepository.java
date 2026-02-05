package com.bsl.bff.ops;

import com.bsl.bff.ops.dto.AutocompleteTrendDto;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class AutocompleteOpsRepository {
    private final JdbcTemplate jdbcTemplate;

    public AutocompleteOpsRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<AutocompleteTrendDto> fetchTrends(String metric, int limit) {
        String orderBy = resolveOrder(metric);
        String sql =
            "SELECT suggest_id, text, type, lang, impressions_7d, clicks_7d, ctr_7d, popularity_7d, last_seen_at, updated_at "
                + "FROM ac_suggest_metric ORDER BY " + orderBy + " DESC LIMIT ?";
        return jdbcTemplate.query(sql, trendMapper(), limit);
    }

    private String resolveOrder(String metric) {
        if (metric == null) {
            return "ctr_7d";
        }
        String normalized = metric.trim().toLowerCase();
        if ("popularity".equals(normalized) || "popularity_7d".equals(normalized)) {
            return "popularity_7d";
        }
        if ("impressions".equals(normalized) || "impressions_7d".equals(normalized)) {
            return "impressions_7d";
        }
        return "ctr_7d";
    }

    private RowMapper<AutocompleteTrendDto> trendMapper() {
        return (rs, rowNum) -> {
            AutocompleteTrendDto dto = new AutocompleteTrendDto();
            dto.setSuggestId(rs.getString("suggest_id"));
            dto.setText(rs.getString("text"));
            dto.setType(rs.getString("type"));
            dto.setLang(rs.getString("lang"));
            dto.setImpressions7d(toDouble(rs, "impressions_7d"));
            dto.setClicks7d(toDouble(rs, "clicks_7d"));
            dto.setCtr7d(toDouble(rs, "ctr_7d"));
            dto.setPopularity7d(toDouble(rs, "popularity_7d"));
            dto.setLastSeenAt(toInstant(rs.getTimestamp("last_seen_at")));
            dto.setUpdatedAt(toInstant(rs.getTimestamp("updated_at")));
            return dto;
        };
    }

    private Double toDouble(ResultSet rs, String column) throws SQLException {
        double value = rs.getDouble(column);
        if (rs.wasNull()) {
            return null;
        }
        return value;
    }

    private Instant toInstant(Timestamp ts) {
        return ts == null ? null : ts.toInstant();
    }
}
