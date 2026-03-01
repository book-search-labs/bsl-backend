package com.bsl.commerce.repository;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.StringJoiner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HomeCollectionRepository {
    private static final String TABLE_NAME = "home_collection_item";

    private final JdbcTemplate jdbcTemplate;
    private volatile Boolean hasCollectionTable;

    public HomeCollectionRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listConfiguredItems(String sectionKey, int limit, Set<String> excludedMaterialIds) {
        if (!isCollectionTableAvailable()) {
            return List.of();
        }

        StringBuilder sql = new StringBuilder()
            .append("SELECT h.material_id AS doc_id, ")
            .append("COALESCE(h.title_override, m.title, m.label, '제목 정보 없음') AS title_ko, ")
            .append("m.publisher AS publisher_name, ")
            .append("m.issued_year AS issued_year, ")
            .append(authorSubquery("h.material_id")).append(" AS author_name ")
            .append("FROM home_collection_item h ")
            .append("LEFT JOIN material m ON m.material_id = h.material_id ")
            .append("WHERE h.section_key = ? ")
            .append("AND h.is_active = 1 ")
            .append("AND (h.starts_at IS NULL OR h.starts_at <= CURRENT_TIMESTAMP) ")
            .append("AND (h.ends_at IS NULL OR h.ends_at >= CURRENT_TIMESTAMP) ");

        List<Object> params = new ArrayList<>();
        params.add(sectionKey);
        appendExclude(sql, params, "h.material_id", excludedMaterialIds);

        sql.append("ORDER BY h.sort_order ASC, h.collection_item_id ASC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public List<Map<String, Object>> listFallbackItems(String sectionKey, int limit, Set<String> excludedMaterialIds) {
        if (limit <= 0) {
            return List.of();
        }

        StringBuilder sql = new StringBuilder()
            .append("SELECT m.material_id AS doc_id, ")
            .append("COALESCE(m.title, m.label, '제목 정보 없음') AS title_ko, ")
            .append("m.publisher AS publisher_name, ")
            .append("m.issued_year AS issued_year, ")
            .append(authorSubquery("m.material_id")).append(" AS author_name ");

        if ("bestseller".equals(sectionKey)) {
            sql.append(", COALESCE(ord.order_qty, 0) AS section_score ");
        } else if ("editor".equals(sectionKey)) {
            sql.append(", (CASE WHEN COALESCE(m.title, m.label, '') REGEXP '에세이|문학|소설|시|인문|철학' THEN 2 ELSE 0 END ")
                .append("+ CASE WHEN EXISTS (")
                .append("SELECT 1 FROM material_kdc mk WHERE mk.material_id = m.material_id ")
                .append("AND mk.kdc_code_3 IN ('100','300','700','800','810','820','830')) ")
                .append("THEN 1 ELSE 0 END) AS section_score ");
        } else {
            sql.append(", COALESCE(m.issued_year, 0) AS section_score ");
        }

        sql.append("FROM material m ");

        if ("bestseller".equals(sectionKey)) {
            sql.append("LEFT JOIN (")
                .append("SELECT s.material_id, SUM(oi.qty) AS order_qty, MAX(o.created_at) AS recent_order_at ")
                .append("FROM order_item oi ")
                .append("JOIN orders o ON o.order_id = oi.order_id ")
                .append("JOIN sku s ON s.sku_id = oi.sku_id ")
                .append("WHERE o.status IN ('PAID','READY_TO_SHIP','SHIPPED','DELIVERED','PARTIALLY_REFUNDED') ")
                .append("AND o.created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 7 DAY) ")
                .append("GROUP BY s.material_id")
                .append(") ord ON ord.material_id = m.material_id ");
        }

        sql.append("WHERE COALESCE(m.title, m.label) IS NOT NULL ")
            .append("AND TRIM(COALESCE(m.title, m.label)) <> '' ");

        List<Object> params = new ArrayList<>();
        appendExclude(sql, params, "m.material_id", excludedMaterialIds);

        String koreanPriority = "CASE WHEN COALESCE(m.title, m.label, '') REGEXP '[가-힣]' THEN 0 ELSE 1 END";
        if ("bestseller".equals(sectionKey)) {
            sql.append("ORDER BY CASE WHEN COALESCE(ord.order_qty, 0) > 0 THEN 0 ELSE 1 END ASC, ")
                .append("COALESCE(ord.order_qty, 0) DESC, ")
                .append(koreanPriority).append(" ASC, ")
                .append("COALESCE(m.issued_year, 0) DESC, ")
                .append("m.material_id ASC ");
        } else if ("new".equals(sectionKey)) {
            sql.append("ORDER BY ").append(koreanPriority).append(" ASC, ")
                .append("COALESCE(m.issued_year, 0) DESC, ")
                .append("COALESCE(m.date_published, '1900-01-01') DESC, ")
                .append("m.updated_at DESC, ")
                .append("m.material_id ASC ");
        } else {
            sql.append("ORDER BY section_score DESC, ")
                .append(koreanPriority).append(" ASC, ")
                .append("COALESCE(m.issued_year, 0) DESC, ")
                .append("m.material_id ASC ");
        }

        sql.append("LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    private String authorSubquery(String materialIdExpr) {
        return "(SELECT COALESCE(a.pref_label, a.label, a.name) "
            + "FROM material_agent ma "
            + "JOIN agent a ON a.agent_id = ma.agent_id "
            + "WHERE ma.material_id = " + materialIdExpr + " "
            + "ORDER BY CASE WHEN ma.role = 'CREATOR' THEN 0 ELSE 1 END, a.pref_label, a.label, a.name "
            + "LIMIT 1)";
    }

    private void appendExclude(StringBuilder sql, List<Object> params, String column, Set<String> excludedMaterialIds) {
        if (excludedMaterialIds == null || excludedMaterialIds.isEmpty()) {
            return;
        }
        StringJoiner joiner = new StringJoiner(", ");
        for (String materialId : excludedMaterialIds) {
            if (materialId == null || materialId.isBlank()) {
                continue;
            }
            joiner.add("?");
            params.add(materialId);
        }
        String placeholders = joiner.toString();
        if (placeholders.isBlank()) {
            return;
        }
        sql.append("AND ").append(column).append(" NOT IN (").append(placeholders).append(") ");
    }

    private boolean isCollectionTableAvailable() {
        Boolean cached = hasCollectionTable;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (hasCollectionTable != null) {
                return hasCollectionTable;
            }
            try {
                Integer count = jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM information_schema.tables "
                        + "WHERE table_schema = DATABASE() "
                        + "AND table_name = ?",
                    Integer.class,
                    TABLE_NAME
                );
                hasCollectionTable = count != null && count > 0;
            } catch (Exception ex) {
                hasCollectionTable = false;
            }
            return hasCollectionTable;
        }
    }
}
