package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.service.CartService;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CartController {
    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @GetMapping("/cart")
    public Map<String, Object> getCart(@RequestHeader(value = "x-user-id", required = false) String userIdHeader) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> summary = cartService.loadCartSummary(userId);
        if (summary == null) {
            cartService.getOrCreateCart(userId);
            summary = cartService.loadCartSummary(userId);
        }
        Map<String, Object> response = base();
        response.put("cart", summary);
        return response;
    }

    @PostMapping("/cart/items")
    public Map<String, Object> addItem(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @RequestBody CartItemRequest request
    ) {
        if (request == null || request.skuId == null || request.qty == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "sku_id and qty are required");
        }
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        long sellerId = request.sellerId == null ? 1L : request.sellerId;
        Map<String, Object> cart = cartService.addItem(userId, request.skuId, sellerId, request.qty);
        Map<String, Object> response = base();
        response.put("cart", cart);
        return response;
    }

    @PatchMapping("/cart/items/{cartItemId}")
    public Map<String, Object> updateItem(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long cartItemId,
        @RequestBody CartItemUpdateRequest request
    ) {
        if (request == null || request.qty == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty is required");
        }
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> cart = cartService.updateItem(userId, cartItemId, request.qty);
        Map<String, Object> response = base();
        response.put("cart", cart);
        return response;
    }

    @DeleteMapping("/cart/items/{cartItemId}")
    public Map<String, Object> removeItem(
        @RequestHeader(value = "x-user-id", required = false) String userIdHeader,
        @PathVariable long cartItemId
    ) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> cart = cartService.removeItem(userId, cartItemId);
        Map<String, Object> response = base();
        response.put("cart", cart);
        return response;
    }

    @DeleteMapping("/cart/items")
    public Map<String, Object> clearCart(@RequestHeader(value = "x-user-id", required = false) String userIdHeader) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> cart = cartService.clearCart(userId);
        Map<String, Object> response = base();
        response.put("cart", cart);
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

    public static class CartItemRequest {
        public Long skuId;
        public Long sellerId;
        public Integer qty;
    }

    public static class CartItemUpdateRequest {
        public Integer qty;
    }
}
