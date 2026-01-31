package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.CatalogService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CatalogController {
    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/skus")
    public Map<String, Object> listSkus(@RequestParam(name = "materialId") String materialId) {
        if (materialId == null || materialId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "materialId is required");
        }
        List<Map<String, Object>> items = catalogService.listSkusByMaterialId(materialId);
        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        return response;
    }

    @GetMapping("/skus/{skuId}")
    public Map<String, Object> getSku(@PathVariable long skuId) {
        Map<String, Object> sku = catalogService.getSku(skuId);
        Map<String, Object> response = base();
        response.put("sku", sku);
        return response;
    }

    @GetMapping("/skus/{skuId}/offers")
    public Map<String, Object> listOffers(@PathVariable long skuId) {
        List<Map<String, Object>> offers = catalogService.listOffersBySkuId(skuId);
        Map<String, Object> response = base();
        response.put("items", offers);
        response.put("count", offers.size());
        return response;
    }

    @GetMapping("/skus/{skuId}/current-offer")
    public Map<String, Object> currentOffer(@PathVariable long skuId) {
        Map<String, Object> offer = catalogService.getCurrentOfferBySkuId(skuId);
        if (offer == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "current_offer_not_found", "no active offer");
        }
        Map<String, Object> response = base();
        response.put("current_offer", offer);
        return response;
    }

    @GetMapping("/materials/{materialId}/current-offer")
    public Map<String, Object> currentOfferByMaterial(@PathVariable String materialId) {
        Map<String, Object> offer = catalogService.getCurrentOfferByMaterialId(materialId);
        if (offer == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "current_offer_not_found", "no active offer");
        }
        Map<String, Object> response = base();
        response.put("current_offer", offer);
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
}
