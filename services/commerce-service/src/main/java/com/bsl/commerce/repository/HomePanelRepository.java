package com.bsl.commerce.repository;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HomePanelRepository {
    private static final String ACTIVE_WINDOW_WHERE =
        " WHERE is_active = 1 "
            + "AND (starts_at IS NULL OR starts_at <= CURRENT_TIMESTAMP) "
            + "AND (ends_at IS NULL OR ends_at >= CURRENT_TIMESTAMP)";
    private static final String TABLE_NAME = "home_panel_item";
    private static final String COLUMN_DETAIL_BODY = "detail_body";
    private static final String COLUMN_BANNER_IMAGE_URL = "banner_image_url";

    private final JdbcTemplate jdbcTemplate;
    private volatile ColumnSupport cachedColumnSupport;

    public HomePanelRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listActiveItems(String panelType, int limit) {
        StringBuilder sql = new StringBuilder(panelSelectFields()).append(ACTIVE_WINDOW_WHERE);

        List<Object> params = new ArrayList<>();
        if (panelType != null) {
            sql.append(" AND panel_type = ?");
            params.add(panelType);
        }

        sql.append(" ORDER BY sort_order ASC, panel_item_id ASC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public Map<String, Object> findActiveItemById(long itemId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            panelSelectFields()
                + ACTIVE_WINDOW_WHERE
                + " AND panel_item_id = ? "
                + "LIMIT 1",
            itemId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long countActiveItems(String panelType) {
        StringBuilder sql = new StringBuilder(
            "SELECT COUNT(*) "
                + "FROM home_panel_item "
        ).append(ACTIVE_WINDOW_WHERE);

        List<Object> params = new ArrayList<>();
        if (panelType != null) {
            sql.append(" AND panel_type = ?");
            params.add(panelType);
        }

        Long count = jdbcTemplate.queryForObject(sql.toString(), Long.class, params.toArray());
        return count == null ? 0L : count;
    }

    private String panelSelectFields() {
        ColumnSupport support = resolveColumnSupport();
        String detailBodyColumn = support.detailBody ? COLUMN_DETAIL_BODY : "NULL";
        String bannerImageColumn = support.bannerImageUrl ? COLUMN_BANNER_IMAGE_URL : "NULL";
        return "SELECT panel_item_id AS item_id, panel_type AS type, badge, title, subtitle, summary, "
            + detailBodyColumn + " AS detail_body, "
            + "link_url, cta_label, "
            + bannerImageColumn + " AS banner_image_url, "
            + "starts_at, ends_at, sort_order "
            + "FROM " + TABLE_NAME + " ";
    }

    private ColumnSupport resolveColumnSupport() {
        ColumnSupport cached = cachedColumnSupport;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (cachedColumnSupport != null) {
                return cachedColumnSupport;
            }
            cachedColumnSupport = new ColumnSupport(
                hasColumn(COLUMN_DETAIL_BODY),
                hasColumn(COLUMN_BANNER_IMAGE_URL)
            );
            return cachedColumnSupport;
        }
    }

    private boolean hasColumn(String columnName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.columns "
                    + "WHERE table_schema = DATABASE() "
                    + "AND table_name = ? "
                    + "AND column_name = ?",
                Integer.class,
                TABLE_NAME,
                columnName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }

    private static final class ColumnSupport {
        private final boolean detailBody;
        private final boolean bannerImageUrl;

        private ColumnSupport(boolean detailBody, boolean bannerImageUrl) {
            this.detailBody = detailBody;
            this.bannerImageUrl = bannerImageUrl;
        }
    }
}
