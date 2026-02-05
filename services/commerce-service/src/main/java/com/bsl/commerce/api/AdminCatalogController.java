package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.repository.SellerRepository;
import com.bsl.commerce.repository.SkuOfferRepository;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin")
public class AdminCatalogController {
    private final SellerRepository sellerRepository;
    private final SkuOfferRepository skuOfferRepository;

    public AdminCatalogController(SellerRepository sellerRepository, SkuOfferRepository skuOfferRepository) {
        this.sellerRepository = sellerRepository;
        this.skuOfferRepository = skuOfferRepository;
    }

    @GetMapping("/sellers")
    public Map<String, Object> listSellers(@RequestParam(name = "limit", required = false) Integer limit) {
        int resolved = limit == null ? 50 : Math.min(Math.max(limit, 1), 200);
        List<Map<String, Object>> sellers = sellerRepository.listSellers(resolved);
        Map<String, Object> response = base();
        response.put("items", sellers);
        response.put("count", sellers.size());
        return response;
    }

    @GetMapping("/sellers/{sellerId}")
    public Map<String, Object> getSeller(@PathVariable long sellerId) {
        Map<String, Object> seller = sellerRepository.findSeller(sellerId);
        if (seller == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "seller not found");
        }
        Map<String, Object> response = base();
        response.put("seller", seller);
        return response;
    }

    @PostMapping("/sellers")
    public Map<String, Object> createSeller(@RequestBody SellerRequest request) {
        if (request == null || request.name == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "name is required");
        }
        long sellerId = sellerRepository.insertSeller(request.name, request.status == null ? "ACTIVE" : request.status,
            request.policyJson);
        Map<String, Object> response = base();
        response.put("seller", sellerRepository.findSeller(sellerId));
        return response;
    }

    @PatchMapping("/sellers/{sellerId}")
    public Map<String, Object> updateSeller(@PathVariable long sellerId, @RequestBody SellerRequest request) {
        if (request == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "request body is required");
        }
        sellerRepository.updateSeller(sellerId, request.name, request.status, request.policyJson);
        Map<String, Object> response = base();
        response.put("seller", sellerRepository.findSeller(sellerId));
        return response;
    }

    @GetMapping("/skus")
    public Map<String, Object> listSkus(@RequestParam(name = "limit", required = false) Integer limit) {
        int resolved = limit == null ? 50 : Math.min(Math.max(limit, 1), 200);
        List<Map<String, Object>> skus = skuOfferRepository.listSkus(resolved);
        Map<String, Object> response = base();
        response.put("items", skus);
        response.put("count", skus.size());
        return response;
    }

    @GetMapping("/skus/{skuId}")
    public Map<String, Object> getSku(@PathVariable long skuId) {
        Map<String, Object> sku = skuOfferRepository.findSkuById(skuId);
        if (sku == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "sku not found");
        }
        Map<String, Object> response = base();
        response.put("sku", sku);
        return response;
    }

    @PostMapping("/skus")
    public Map<String, Object> createSku(@RequestBody SkuRequest request) {
        if (request == null || request.materialId == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "material_id is required");
        }
        long skuId = skuOfferRepository.insertSku(
            request.materialId,
            request.sellerId,
            request.skuCode,
            request.format,
            request.edition,
            request.packSize,
            request.status == null ? "ACTIVE" : request.status,
            request.attrsJson
        );
        Map<String, Object> response = base();
        response.put("sku", skuOfferRepository.findSkuById(skuId));
        return response;
    }

    @PatchMapping("/skus/{skuId}")
    public Map<String, Object> updateSku(@PathVariable long skuId, @RequestBody SkuRequest request) {
        if (request == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "request body is required");
        }
        skuOfferRepository.updateSku(
            skuId,
            request.materialId,
            request.sellerId,
            request.skuCode,
            request.format,
            request.edition,
            request.packSize,
            request.status,
            request.attrsJson
        );
        Map<String, Object> response = base();
        response.put("sku", skuOfferRepository.findSkuById(skuId));
        return response;
    }

    @GetMapping("/offers")
    public Map<String, Object> listOffers(@RequestParam(name = "sku_id") long skuId) {
        List<Map<String, Object>> offers = skuOfferRepository.findOffersBySkuId(skuId);
        Map<String, Object> response = base();
        response.put("items", offers);
        response.put("count", offers.size());
        return response;
    }

    @PostMapping("/offers")
    public Map<String, Object> createOffer(@RequestBody OfferRequest request) {
        if (request == null || request.skuId == null || request.sellerId == null || request.listPrice == null
            || request.salePrice == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "sku_id, seller_id, list_price, sale_price required");
        }
        long offerId = skuOfferRepository.insertOffer(
            request.skuId,
            request.sellerId,
            request.currency == null ? "KRW" : request.currency,
            request.listPrice,
            request.salePrice,
            request.status == null ? "ACTIVE" : request.status,
            request.priority,
            request.startAt,
            request.endAt,
            request.shippingPolicyJson,
            request.purchaseLimitJson
        );
        Map<String, Object> response = base();
        response.put("offer_id", offerId);
        response.put("offer", skuOfferRepository.findOffersBySkuId(request.skuId).stream()
            .filter(row -> offerId == com.bsl.commerce.common.JdbcUtils.asLong(row.get("offer_id")))
            .findFirst().orElse(null));
        return response;
    }

    @PatchMapping("/offers/{offerId}")
    public Map<String, Object> updateOffer(@PathVariable long offerId, @RequestBody OfferRequest request) {
        if (request == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "request body is required");
        }
        skuOfferRepository.updateOffer(
            offerId,
            request.skuId,
            request.sellerId,
            request.currency == null ? "KRW" : request.currency,
            request.listPrice == null ? 0 : request.listPrice,
            request.salePrice == null ? 0 : request.salePrice,
            request.status,
            request.priority,
            request.startAt,
            request.endAt,
            request.shippingPolicyJson,
            request.purchaseLimitJson
        );
        Map<String, Object> response = base();
        response.put("offer_id", offerId);
        response.put("offer", skuOfferRepository.findOffersBySkuId(request.skuId).stream()
            .filter(row -> offerId == com.bsl.commerce.common.JdbcUtils.asLong(row.get("offer_id")))
            .findFirst().orElse(null));
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

    public static class SellerRequest {
        public String name;
        public String status;
        public String policyJson;
    }

    public static class SkuRequest {
        public String materialId;
        public Long sellerId;
        public String skuCode;
        public String format;
        public String edition;
        public Integer packSize;
        public String status;
        public String attrsJson;
    }

    public static class OfferRequest {
        public Long skuId;
        public Long sellerId;
        public String currency;
        public Integer listPrice;
        public Integer salePrice;
        public String status;
        public Integer priority;
        public String startAt;
        public String endAt;
        public String shippingPolicyJson;
        public String purchaseLimitJson;
    }
}
