package com.bsl.commerce.repository;

import com.bsl.commerce.common.PriceUtils;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class SkuOfferRepository {
    private final JdbcTemplate jdbcTemplate;

    public SkuOfferRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> findSkusByMaterialId(String materialId) {
        return jdbcTemplate.queryForList(
            "SELECT sku_id, material_id, seller_id, sku_code, format, edition, pack_size, status, attrs_json, created_at, updated_at "
                + "FROM sku WHERE material_id = ? ORDER BY sku_id DESC",
            materialId
        );
    }

    public boolean materialExists(String materialId) {
        Integer value = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM material WHERE material_id = ?",
            Integer.class,
            materialId
        );
        return value != null && value > 0;
    }

    public boolean lockMaterialRow(String materialId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT material_id FROM material WHERE material_id = ? FOR UPDATE",
            materialId
        );
        return !rows.isEmpty();
    }

    public Map<String, Object> findSkuByMaterialIdAndSeller(String materialId, long sellerId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT sku_id, material_id, seller_id, sku_code, format, edition, pack_size, status, attrs_json, created_at, updated_at "
                + "FROM sku WHERE material_id = ? AND seller_id = ? ORDER BY sku_id DESC LIMIT 1",
            materialId,
            sellerId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findSkuById(long skuId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT sku_id, material_id, seller_id, sku_code, format, edition, pack_size, status, attrs_json, created_at, updated_at "
                + "FROM sku WHERE sku_id = ?",
            skuId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Map<String, Object> findSkuDisplayInfo(long skuId, long sellerId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT s.sku_id, s.material_id, s.format, s.edition, s.pack_size, "
                + "m.title AS material_title, m.subtitle AS material_subtitle, m.label AS material_label, "
                + "m.publisher AS material_publisher, m.issued_year AS material_issued_year, "
                + "sl.name AS seller_name, "
                + "(SELECT COALESCE(a.pref_label, a.label, a.name) "
                + "  FROM material_agent ma "
                + "  JOIN agent a ON a.agent_id = ma.agent_id "
                + "  WHERE ma.material_id = s.material_id "
                + "  ORDER BY CASE WHEN ma.role = 'CREATOR' THEN 0 ELSE 1 END, a.pref_label, a.label, a.name "
                + "  LIMIT 1) AS creator_name "
                + "FROM sku s "
                + "LEFT JOIN material m ON m.material_id = s.material_id "
                + "LEFT JOIN seller sl ON sl.seller_id = ? "
                + "WHERE s.sku_id = ?",
            sellerId,
            skuId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Map<String, Object>> listSkus(int limit) {
        return jdbcTemplate.queryForList(
            "SELECT sku_id, material_id, seller_id, sku_code, format, edition, pack_size, status, attrs_json, created_at, updated_at "
                + "FROM sku ORDER BY sku_id DESC LIMIT ?",
            limit
        );
    }

    public long insertSku(
        String materialId,
        Long sellerId,
        String skuCode,
        String format,
        String edition,
        Integer packSize,
        String status,
        String attrsJson
    ) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO sku (material_id, seller_id, sku_code, format, edition, pack_size, status, attrs_json) "
                    + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, materialId);
            if (sellerId == null) {
                ps.setObject(2, null);
            } else {
                ps.setLong(2, sellerId);
            }
            ps.setString(3, skuCode);
            ps.setString(4, format);
            ps.setString(5, edition);
            if (packSize == null) {
                ps.setObject(6, null);
            } else {
                ps.setInt(6, packSize);
            }
            ps.setString(7, status);
            ps.setString(8, attrsJson);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void updateSku(
        long skuId,
        String materialId,
        Long sellerId,
        String skuCode,
        String format,
        String edition,
        Integer packSize,
        String status,
        String attrsJson
    ) {
        jdbcTemplate.update(
            "UPDATE sku SET material_id = ?, seller_id = ?, sku_code = ?, format = ?, edition = ?, pack_size = ?, "
                + "status = ?, attrs_json = ? WHERE sku_id = ?",
            materialId,
            sellerId,
            skuCode,
            format,
            edition,
            packSize,
            status,
            attrsJson,
            skuId
        );
    }

    public List<Map<String, Object>> findOffersBySkuId(long skuId) {
        return jdbcTemplate.queryForList(
            "SELECT offer_id, sku_id, seller_id, currency, list_price, sale_price, start_at, end_at, status, priority, "
                + "shipping_policy_json, purchase_limit_json, created_at, updated_at "
                + "FROM offer WHERE sku_id = ? ORDER BY created_at DESC",
            skuId
        );
    }

    public Map<String, Object> findCurrentOfferBySkuId(long skuId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT offer_id, sku_id, seller_id, currency, list_price, sale_price, start_at, end_at, status, priority, "
                + "shipping_policy_json, purchase_limit_json, created_at, updated_at "
                + "FROM offer WHERE sku_id = ? AND status = 'ACTIVE' "
                + "AND (start_at IS NULL OR start_at <= UTC_TIMESTAMP()) "
                + "AND (end_at IS NULL OR end_at > UTC_TIMESTAMP()) "
                + "ORDER BY priority DESC, created_at DESC LIMIT 1",
            skuId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public int countActiveOffersBySkuId(long skuId) {
        Integer value = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM offer WHERE sku_id = ? AND status = 'ACTIVE' "
                + "AND (start_at IS NULL OR start_at <= UTC_TIMESTAMP()) "
                + "AND (end_at IS NULL OR end_at > UTC_TIMESTAMP())",
            Integer.class,
            skuId
        );
        return value == null ? 0 : value;
    }

    public Map<String, Object> findCurrentOfferByMaterialId(String materialId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
            "SELECT o.offer_id, o.sku_id, o.seller_id, o.currency, o.list_price, o.sale_price, o.start_at, o.end_at, "
                + "o.status, o.priority, o.shipping_policy_json, o.purchase_limit_json, o.created_at, o.updated_at "
                + "FROM offer o JOIN sku s ON o.sku_id = s.sku_id "
                + "WHERE s.material_id = ? AND o.status = 'ACTIVE' "
                + "AND (o.start_at IS NULL OR o.start_at <= UTC_TIMESTAMP()) "
                + "AND (o.end_at IS NULL OR o.end_at > UTC_TIMESTAMP()) "
                + "ORDER BY o.priority DESC, o.created_at DESC LIMIT 1",
            materialId
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public long insertOffer(
        long skuId,
        long sellerId,
        String currency,
        int listPrice,
        int salePrice,
        String status,
        Integer priority,
        String startAt,
        String endAt,
        String shippingPolicyJson,
        String purchaseLimitJson
    ) {
        int normalizedListPrice = PriceUtils.normalizeBookPrice(listPrice);
        int normalizedSalePrice = PriceUtils.normalizeBookPrice(salePrice);
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO offer (sku_id, seller_id, currency, list_price, sale_price, start_at, end_at, status, "
                    + "priority, shipping_policy_json, purchase_limit_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                Statement.RETURN_GENERATED_KEYS
            );
            ps.setLong(1, skuId);
            ps.setLong(2, sellerId);
            ps.setString(3, currency);
            ps.setInt(4, normalizedListPrice);
            ps.setInt(5, normalizedSalePrice);
            ps.setString(6, startAt);
            ps.setString(7, endAt);
            ps.setString(8, status);
            ps.setInt(9, priority == null ? 0 : priority);
            ps.setString(10, shippingPolicyJson);
            ps.setString(11, purchaseLimitJson);
            return ps;
        }, keyHolder);
        Number key = keyHolder.getKey();
        return key == null ? 0L : key.longValue();
    }

    public void updateOffer(
        long offerId,
        long skuId,
        long sellerId,
        String currency,
        int listPrice,
        int salePrice,
        String status,
        Integer priority,
        String startAt,
        String endAt,
        String shippingPolicyJson,
        String purchaseLimitJson
    ) {
        int normalizedListPrice = PriceUtils.normalizeBookPrice(listPrice);
        int normalizedSalePrice = PriceUtils.normalizeBookPrice(salePrice);
        jdbcTemplate.update(
            "UPDATE offer SET sku_id = ?, seller_id = ?, currency = ?, list_price = ?, sale_price = ?, start_at = ?, "
                + "end_at = ?, status = ?, priority = ?, shipping_policy_json = ?, purchase_limit_json = ? "
                + "WHERE offer_id = ?",
            skuId,
            sellerId,
            currency,
            normalizedListPrice,
            normalizedSalePrice,
            startAt,
            endAt,
            status,
            priority == null ? 0 : priority,
            shippingPolicyJson,
            purchaseLimitJson,
            offerId
        );
    }
}
