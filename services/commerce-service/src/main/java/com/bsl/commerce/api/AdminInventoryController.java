package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.InventoryService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin")
public class AdminInventoryController {
    private final InventoryService inventoryService;

    public AdminInventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/inventory/balance")
    public Map<String, Object> getBalance(
        @RequestParam(name = "sku_id") long skuId,
        @RequestParam(name = "seller_id", required = false) Long sellerId
    ) {
        Map<String, Object> balance = inventoryService.getBalance(skuId, sellerId);
        Map<String, Object> response = base();
        response.put("balance", balance);
        return response;
    }

    @GetMapping("/inventory/ledger")
    public Map<String, Object> getLedger(
        @RequestParam(name = "sku_id") long skuId,
        @RequestParam(name = "seller_id", required = false) Long sellerId,
        @RequestParam(name = "limit", required = false) Integer limit
    ) {
        long resolvedSellerId = sellerId == null ? 1L : sellerId;
        int resolvedLimit = limit == null ? 50 : Math.min(Math.max(limit, 1), 200);
        List<Map<String, Object>> ledger = inventoryService.listLedger(skuId, resolvedSellerId, resolvedLimit);
        Map<String, Object> response = base();
        response.put("items", ledger);
        response.put("count", ledger.size());
        return response;
    }

    @PostMapping("/inventory/adjust")
    public Map<String, Object> adjustInventory(
        @RequestHeader(value = "x-admin-id", required = false) String adminIdHeader,
        @RequestBody InventoryAdjustRequest request
    ) {
        if (request == null || request.skuId == null || request.delta == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "sku_id and delta are required");
        }
        long adminId = RequestUtils.resolveAdminId(adminIdHeader, 1L);
        long sellerId = request.sellerId == null ? 1L : request.sellerId;
        InventoryService.InventoryResult result = inventoryService.adjust(
            request.skuId,
            sellerId,
            request.delta,
            request.idempotencyKey,
            "ADMIN",
            request.refId,
            adminId
        );
        Map<String, Object> response = base();
        response.put("balance", result.balance());
        response.put("ledger", result.ledger());
        return response;
    }

    private Map<String, Object> base() {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new HashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        return response;
    }

    public static class InventoryAdjustRequest {
        public Long skuId;
        public Long sellerId;
        public Integer delta;
        public String idempotencyKey;
        public String refId;
    }
}
