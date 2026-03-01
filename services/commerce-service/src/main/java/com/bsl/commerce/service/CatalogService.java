package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.PriceUtils;
import com.bsl.commerce.repository.InventoryRepository;
import com.bsl.commerce.repository.SellerRepository;
import com.bsl.commerce.repository.SkuOfferRepository;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {
    private static final Logger logger = LoggerFactory.getLogger(CatalogService.class);
    private static final int DEFAULT_ON_HAND_QTY = 40;
    private static final String DEFAULT_SHIPPING_POLICY_JSON = "{\"free_shipping_threshold\":20000,\"returns_days\":7}";
    private static final String DEFAULT_PURCHASE_LIMIT_JSON = "{\"max_qty\":20}";
    private static final String AUTO_SKU_ATTRS_JSON = "{\"auto_provisioned\":true}";

    private final SkuOfferRepository skuOfferRepository;
    private final InventoryRepository inventoryRepository;
    private final SellerRepository sellerRepository;

    public CatalogService(
        SkuOfferRepository skuOfferRepository,
        InventoryRepository inventoryRepository,
        SellerRepository sellerRepository
    ) {
        this.skuOfferRepository = skuOfferRepository;
        this.inventoryRepository = inventoryRepository;
        this.sellerRepository = sellerRepository;
    }

    public List<Map<String, Object>> listSkusByMaterialId(String materialId) {
        List<Map<String, Object>> rows = skuOfferRepository.findSkusByMaterialId(materialId);
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            result.add(toSkuDto(row));
        }
        return result;
    }

    public Map<String, Object> getSku(long skuId) {
        Map<String, Object> row = skuOfferRepository.findSkuById(skuId);
        if (row == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "sku not found");
        }
        return toSkuDto(row);
    }

    public Map<String, Object> getSkuDisplayInfo(long skuId, long sellerId) {
        Map<String, Object> row = skuOfferRepository.findSkuDisplayInfo(skuId, sellerId);
        if (row == null) {
            return null;
        }

        String title = JdbcUtils.asString(row.get("material_title"));
        if (title == null || title.isBlank()) {
            title = JdbcUtils.asString(row.get("material_label"));
        }

        Map<String, Object> dto = new HashMap<>();
        dto.put("material_id", JdbcUtils.asString(row.get("material_id")));
        dto.put("title", title);
        dto.put("subtitle", JdbcUtils.asString(row.get("material_subtitle")));
        dto.put("author", JdbcUtils.asString(row.get("creator_name")));
        dto.put("publisher", JdbcUtils.asString(row.get("material_publisher")));
        dto.put("issued_year", JdbcUtils.asInt(row.get("material_issued_year")));
        dto.put("seller_name", JdbcUtils.asString(row.get("seller_name")));
        dto.put("format", JdbcUtils.asString(row.get("format")));
        dto.put("edition", JdbcUtils.asString(row.get("edition")));
        dto.put("pack_size", JdbcUtils.asInt(row.get("pack_size")));
        return dto;
    }

    public List<Map<String, Object>> listOffersBySkuId(long skuId) {
        List<Map<String, Object>> rows = skuOfferRepository.findOffersBySkuId(skuId);
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            result.add(toOfferDto(row));
        }
        return result;
    }

    public Map<String, Object> getCurrentOfferBySkuId(long skuId) {
        int overlap = skuOfferRepository.countActiveOffersBySkuId(skuId);
        if (overlap > 1) {
            logger.info("offer_overlap_detected sku_id={} count={}", skuId, overlap);
        }
        Map<String, Object> row = skuOfferRepository.findCurrentOfferBySkuId(skuId);
        if (row == null) {
            return null;
        }
        return toCurrentOfferDto(row);
    }

    public Map<String, Object> requireCurrentOfferBySkuId(long skuId) {
        Map<String, Object> current = getCurrentOfferBySkuId(skuId);
        if (current == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "current_offer_not_found", "no active offer");
        }
        return current;
    }

    @Transactional
    public Map<String, Object> getCurrentOfferByMaterialId(String materialId) {
        if (materialId == null || materialId.isBlank()) {
            return null;
        }
        Map<String, Object> row = skuOfferRepository.findCurrentOfferByMaterialId(materialId);
        if (row != null) {
            return toCurrentOfferDto(row);
        }

        if (!skuOfferRepository.lockMaterialRow(materialId)) {
            return null;
        }

        row = skuOfferRepository.findCurrentOfferByMaterialId(materialId);
        if (row != null) {
            return toCurrentOfferDto(row);
        }

        provisionDefaultOffer(materialId);
        Map<String, Object> provisioned = skuOfferRepository.findCurrentOfferByMaterialId(materialId);
        return provisioned == null ? null : toCurrentOfferDto(provisioned);
    }

    private void provisionDefaultOffer(String materialId) {
        if (!skuOfferRepository.materialExists(materialId)) {
            return;
        }

        long sellerId = resolveDefaultSellerId();
        long skuId = resolveOrCreateSku(materialId, sellerId);
        ensureCurrentOffer(skuId, sellerId, materialId);
        ensureInventoryBalance(skuId, sellerId);

        logger.info("catalog_auto_provisioned material_id={} sku_id={} seller_id={}", materialId, skuId, sellerId);
    }

    private long resolveDefaultSellerId() {
        Long sellerId = sellerRepository.findActiveSellerId();
        if (sellerId != null) {
            return sellerId;
        }
        return sellerRepository.insertSeller("BSL Store", "ACTIVE", "{\"auto_provisioned\":true}");
    }

    private long resolveOrCreateSku(String materialId, long sellerId) {
        Map<String, Object> existing = skuOfferRepository.findSkuByMaterialIdAndSeller(materialId, sellerId);
        if (existing != null) {
            Long skuId = JdbcUtils.asLong(existing.get("sku_id"));
            if (skuId != null) {
                return skuId;
            }
        }

        long inserted = skuOfferRepository.insertSku(
            materialId,
            sellerId,
            null,
            "PAPERBACK",
            null,
            1,
            "ACTIVE",
            AUTO_SKU_ATTRS_JSON
        );
        if (inserted > 0) {
            return inserted;
        }

        Map<String, Object> reloaded = skuOfferRepository.findSkuByMaterialIdAndSeller(materialId, sellerId);
        if (reloaded != null) {
            Long skuId = JdbcUtils.asLong(reloaded.get("sku_id"));
            if (skuId != null) {
                return skuId;
            }
        }
        throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "sku_create_failed", "failed to provision sku");
    }

    private void ensureCurrentOffer(long skuId, long sellerId, String materialId) {
        Map<String, Object> offer = skuOfferRepository.findCurrentOfferBySkuId(skuId);
        if (offer != null) {
            return;
        }

        int listPrice = resolveListPrice(materialId);
        int salePrice = resolveSalePrice(listPrice);

        skuOfferRepository.insertOffer(
            skuId,
            sellerId,
            "KRW",
            listPrice,
            salePrice,
            "ACTIVE",
            0,
            null,
            null,
            DEFAULT_SHIPPING_POLICY_JSON,
            DEFAULT_PURCHASE_LIMIT_JSON
        );
    }

    private void ensureInventoryBalance(long skuId, long sellerId) {
        Map<String, Object> balance = inventoryRepository.findBalance(skuId, sellerId);
        if (balance == null) {
            inventoryRepository.insertBalance(skuId, sellerId, DEFAULT_ON_HAND_QTY, 0);
            return;
        }
        Integer onHand = JdbcUtils.asInt(balance.get("on_hand"));
        Integer reserved = JdbcUtils.asInt(balance.get("reserved"));
        if ((onHand == null || onHand <= 0) && (reserved == null || reserved == 0)) {
            inventoryRepository.updateBalance(skuId, sellerId, DEFAULT_ON_HAND_QTY, 0);
        }
    }

    private int resolveListPrice(String materialId) {
        long hash = Integer.toUnsignedLong(materialId.hashCode());
        return PriceUtils.normalizeBookPrice(12000 + (int) (hash % 26000L));
    }

    private int resolveSalePrice(int listPrice) {
        int discount = Math.max(1200, listPrice / 8);
        return PriceUtils.normalizeBookPrice(Math.max(3000, listPrice - discount));
    }

    private Map<String, Object> toSkuDto(Map<String, Object> row) {
        Map<String, Object> dto = new HashMap<>();
        dto.put("sku_id", JdbcUtils.asLong(row.get("sku_id")));
        dto.put("material_id", JdbcUtils.asString(row.get("material_id")));
        dto.put("seller_id", JdbcUtils.asLong(row.get("seller_id")));
        dto.put("sku_code", JdbcUtils.asString(row.get("sku_code")));
        dto.put("format", JdbcUtils.asString(row.get("format")));
        dto.put("edition", JdbcUtils.asString(row.get("edition")));
        dto.put("pack_size", JdbcUtils.asInt(row.get("pack_size")));
        dto.put("status", JdbcUtils.asString(row.get("status")));
        dto.put("attrs_json", JdbcUtils.asString(row.get("attrs_json")));
        dto.put("created_at", JdbcUtils.asIsoString(row.get("created_at")));
        dto.put("updated_at", JdbcUtils.asIsoString(row.get("updated_at")));
        return dto;
    }

    private Map<String, Object> toOfferDto(Map<String, Object> row) {
        Map<String, Object> dto = new HashMap<>();
        dto.put("offer_id", JdbcUtils.asLong(row.get("offer_id")));
        dto.put("sku_id", JdbcUtils.asLong(row.get("sku_id")));
        dto.put("seller_id", JdbcUtils.asLong(row.get("seller_id")));
        dto.put("currency", JdbcUtils.asString(row.get("currency")));
        dto.put("list_price", PriceUtils.normalizeBookPrice(JdbcUtils.asInt(row.get("list_price"))));
        dto.put("sale_price", PriceUtils.normalizeBookPrice(JdbcUtils.asInt(row.get("sale_price"))));
        dto.put("start_at", JdbcUtils.asIsoString(row.get("start_at")));
        dto.put("end_at", JdbcUtils.asIsoString(row.get("end_at")));
        dto.put("status", JdbcUtils.asString(row.get("status")));
        dto.put("priority", JdbcUtils.asInt(row.get("priority")));
        dto.put("shipping_policy_json", JdbcUtils.asString(row.get("shipping_policy_json")));
        dto.put("purchase_limit_json", JdbcUtils.asString(row.get("purchase_limit_json")));
        dto.put("created_at", JdbcUtils.asIsoString(row.get("created_at")));
        dto.put("updated_at", JdbcUtils.asIsoString(row.get("updated_at")));
        return dto;
    }

    private Map<String, Object> toCurrentOfferDto(Map<String, Object> row) {
        Map<String, Object> dto = toOfferDto(row);
        Integer salePrice = PriceUtils.normalizeBookPrice(JdbcUtils.asInt(row.get("sale_price")));
        Integer listPrice = PriceUtils.normalizeBookPrice(JdbcUtils.asInt(row.get("list_price")));
        int effectivePrice = salePrice != null ? salePrice : (listPrice == null ? 0 : listPrice);
        dto.put("effective_price", effectivePrice);
        Long skuId = JdbcUtils.asLong(row.get("sku_id"));
        Long sellerId = JdbcUtils.asLong(row.get("seller_id"));
        if (skuId != null && sellerId != null) {
            Map<String, Object> balance = inventoryRepository.findBalance(skuId, sellerId);
            Integer available = balance == null ? null : JdbcUtils.asInt(balance.get("available"));
            dto.put("available_qty", available);
            dto.put("is_in_stock", available != null && available > 0);
        } else {
            dto.put("available_qty", null);
            dto.put("is_in_stock", null);
        }
        return dto;
    }
}
