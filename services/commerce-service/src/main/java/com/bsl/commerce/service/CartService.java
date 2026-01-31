package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.CartRepository;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final CartRepository cartRepository;
    private final CatalogService catalogService;
    private final InventoryService inventoryService;
    private final CommerceProperties properties;

    public CartService(
        CartRepository cartRepository,
        CatalogService catalogService,
        InventoryService inventoryService,
        CommerceProperties properties
    ) {
        this.cartRepository = cartRepository;
        this.catalogService = catalogService;
        this.inventoryService = inventoryService;
        this.properties = properties;
    }

    @Transactional
    public Map<String, Object> getOrCreateCart(long userId) {
        Map<String, Object> cart = cartRepository.findCartByUserId(userId);
        if (cart == null) {
            long cartId = cartRepository.insertCart(userId);
            cart = cartRepository.findCartById(cartId);
        }
        return cart;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> loadCartSummary(long userId) {
        Map<String, Object> cart = cartRepository.findCartByUserId(userId);
        if (cart == null) {
            return null;
        }
        return buildCartSummary(cart, cartRepository.listCartItems(JdbcUtils.asLong(cart.get("cart_id"))));
    }

    @Transactional
    public Map<String, Object> addItem(long userId, long skuId, long sellerId, int qty) {
        if (qty < 1 || qty > properties.getCart().getMaxQtyPerItem()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty out of range");
        }
        Map<String, Object> cart = getOrCreateCart(userId);
        long cartId = JdbcUtils.asLong(cart.get("cart_id"));

        int distinctCount = cartRepository.countDistinctItems(cartId);
        boolean exists = cartRepository.listCartItems(cartId).stream()
            .anyMatch(item -> skuId == JdbcUtils.asLong(item.get("sku_id")) && sellerId == JdbcUtils.asLong(item.get("seller_id")));
        if (!exists && distinctCount >= properties.getCart().getMaxDistinctItems()) {
            throw new ApiException(HttpStatus.CONFLICT, "cart_item_limit", "cart item limit reached");
        }

        Map<String, Object> currentOffer = catalogService.requireCurrentOfferBySkuId(skuId);
        Long currentSellerId = JdbcUtils.asLong(currentOffer.get("seller_id"));
        if (currentSellerId != null && currentSellerId != sellerId) {
            throw new ApiException(HttpStatus.CONFLICT, "seller_mismatch", "offer seller mismatch");
        }
        Long offerId = JdbcUtils.asLong(currentOffer.get("offer_id"));
        Integer unitPrice = JdbcUtils.asInt(currentOffer.get("effective_price"));
        String currency = JdbcUtils.asString(currentOffer.get("currency"));
        java.time.Instant capturedAt = java.time.Instant.now();

        cartRepository.upsertCartItem(cartId, skuId, sellerId, qty, offerId, unitPrice, currency, capturedAt);
        cartRepository.touchCart(cartId);
        return buildCartSummary(cartRepository.findCartById(cartId), cartRepository.listCartItems(cartId));
    }

    @Transactional
    public Map<String, Object> updateItem(long userId, long cartItemId, int qty) {
        if (qty < 1 || qty > properties.getCart().getMaxQtyPerItem()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty out of range");
        }
        Map<String, Object> cartItem = cartRepository.findCartItemById(cartItemId);
        if (cartItem == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "cart item not found");
        }
        long cartId = JdbcUtils.asLong(cartItem.get("cart_id"));
        Map<String, Object> cart = cartRepository.findCartById(cartId);
        if (cart == null || JdbcUtils.asLong(cart.get("user_id")) != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "cart item does not belong to user");
        }

        long skuId = JdbcUtils.asLong(cartItem.get("sku_id"));
        Map<String, Object> currentOffer = catalogService.requireCurrentOfferBySkuId(skuId);
        Long offerId = JdbcUtils.asLong(currentOffer.get("offer_id"));
        Integer unitPrice = JdbcUtils.asInt(currentOffer.get("effective_price"));
        String currency = JdbcUtils.asString(currentOffer.get("currency"));
        java.time.Instant capturedAt = java.time.Instant.now();

        cartRepository.updateCartItemQty(cartItemId, qty, offerId, unitPrice, currency, capturedAt);
        cartRepository.touchCart(cartId);
        return buildCartSummary(cart, cartRepository.listCartItems(cartId));
    }

    @Transactional
    public Map<String, Object> removeItem(long userId, long cartItemId) {
        Map<String, Object> cartItem = cartRepository.findCartItemById(cartItemId);
        if (cartItem == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "cart item not found");
        }
        long cartId = JdbcUtils.asLong(cartItem.get("cart_id"));
        Map<String, Object> cart = cartRepository.findCartById(cartId);
        if (cart == null || JdbcUtils.asLong(cart.get("user_id")) != userId) {
            throw new ApiException(HttpStatus.FORBIDDEN, "forbidden", "cart item does not belong to user");
        }
        cartRepository.deleteCartItem(cartItemId);
        cartRepository.touchCart(cartId);
        return buildCartSummary(cart, cartRepository.listCartItems(cartId));
    }

    @Transactional
    public Map<String, Object> clearCart(long userId) {
        Map<String, Object> cart = cartRepository.findCartByUserId(userId);
        if (cart == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "cart not found");
        }
        long cartId = JdbcUtils.asLong(cart.get("cart_id"));
        cartRepository.clearCart(cartId);
        cartRepository.touchCart(cartId);
        return buildCartSummary(cart, List.of());
    }

    public Map<String, Object> buildCartSummary(Map<String, Object> cart, List<Map<String, Object>> items) {
        Map<String, Object> response = new HashMap<>();
        response.put("cart_id", JdbcUtils.asLong(cart.get("cart_id")));
        response.put("user_id", JdbcUtils.asLong(cart.get("user_id")));
        response.put("status", JdbcUtils.asString(cart.get("status")));
        response.put("created_at", JdbcUtils.asIsoString(cart.get("created_at")));
        response.put("updated_at", JdbcUtils.asIsoString(cart.get("updated_at")));

        List<Map<String, Object>> mappedItems = new ArrayList<>();
        int subtotal = 0;
        for (Map<String, Object> item : items) {
            Map<String, Object> mapped = new HashMap<>();
            long skuId = JdbcUtils.asLong(item.get("sku_id"));
            long sellerId = JdbcUtils.asLong(item.get("seller_id"));
            int qty = JdbcUtils.asInt(item.get("qty"));
            Integer unitPrice = JdbcUtils.asInt(item.get("unit_price"));
            int itemAmount = (unitPrice == null ? 0 : unitPrice) * qty;
            subtotal += itemAmount;

            mapped.put("cart_item_id", JdbcUtils.asLong(item.get("cart_item_id")));
            mapped.put("sku_id", skuId);
            mapped.put("seller_id", sellerId);
            mapped.put("qty", qty);
            mapped.put("offer_id", JdbcUtils.asLong(item.get("offer_id")));
            mapped.put("unit_price", unitPrice);
            mapped.put("currency", JdbcUtils.asString(item.get("currency")));
            mapped.put("captured_at", JdbcUtils.asIsoString(item.get("captured_at")));
            mapped.put("item_amount", itemAmount);
            mapped.put("added_at", JdbcUtils.asIsoString(item.get("added_at")));
            mapped.put("updated_at", JdbcUtils.asIsoString(item.get("updated_at")));

            Map<String, Object> currentOffer = catalogService.getCurrentOfferBySkuId(skuId);
            if (currentOffer == null) {
                mapped.put("price_changed", true);
                mapped.put("current_price", null);
                mapped.put("offer_active", false);
            } else {
                Integer currentPrice = JdbcUtils.asInt(currentOffer.get("effective_price"));
                Long currentOfferId = JdbcUtils.asLong(currentOffer.get("offer_id"));
                mapped.put("current_price", currentPrice);
                boolean priceChanged = currentPrice != null && unitPrice != null && !currentPrice.equals(unitPrice);
                boolean offerChanged = currentOfferId != null && !currentOfferId.equals(JdbcUtils.asLong(item.get("offer_id")));
                mapped.put("price_changed", priceChanged || offerChanged);
                mapped.put("offer_active", true);
                mapped.put("current_offer_id", currentOfferId);
            }

            try {
                Map<String, Object> balance = inventoryService.getBalance(skuId, sellerId);
                Integer available = JdbcUtils.asInt(balance.get("available"));
                mapped.put("available_qty", available);
                mapped.put("out_of_stock", available != null && available < qty);
            } catch (ApiException ex) {
                mapped.put("available_qty", null);
                mapped.put("out_of_stock", null);
            }

            mappedItems.add(mapped);
        }

        response.put("items", mappedItems);
        Map<String, Object> totals = new HashMap<>();
        totals.put("subtotal", subtotal);
        totals.put("shipping_fee", 0);
        totals.put("discount", 0);
        totals.put("total", subtotal);
        response.put("totals", totals);
        return response;
    }
}
