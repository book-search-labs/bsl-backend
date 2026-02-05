package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.InventoryRepository;
import com.bsl.commerce.repository.SkuOfferRepository;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private static final Logger logger = LoggerFactory.getLogger(CatalogService.class);

    private final SkuOfferRepository skuOfferRepository;
    private final InventoryRepository inventoryRepository;

    public CatalogService(SkuOfferRepository skuOfferRepository, InventoryRepository inventoryRepository) {
        this.skuOfferRepository = skuOfferRepository;
        this.inventoryRepository = inventoryRepository;
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

    public Map<String, Object> getCurrentOfferByMaterialId(String materialId) {
        Map<String, Object> row = skuOfferRepository.findCurrentOfferByMaterialId(materialId);
        if (row == null) {
            return null;
        }
        return toCurrentOfferDto(row);
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
        dto.put("list_price", JdbcUtils.asInt(row.get("list_price")));
        dto.put("sale_price", JdbcUtils.asInt(row.get("sale_price")));
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
        Integer salePrice = JdbcUtils.asInt(row.get("sale_price"));
        Integer listPrice = JdbcUtils.asInt(row.get("list_price"));
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
