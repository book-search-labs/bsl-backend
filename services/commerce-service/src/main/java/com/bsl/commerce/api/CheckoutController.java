package com.bsl.commerce.api;

import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.common.RequestUtils;
import com.bsl.commerce.repository.AddressRepository;
import com.bsl.commerce.service.CartService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CheckoutController {
    private final CartService cartService;
    private final AddressRepository addressRepository;

    public CheckoutController(CartService cartService, AddressRepository addressRepository) {
        this.cartService = cartService;
        this.addressRepository = addressRepository;
    }

    @GetMapping("/checkout")
    public Map<String, Object> getCheckout(@RequestHeader(value = "x-user-id", required = false) String userIdHeader) {
        long userId = RequestUtils.resolveUserId(userIdHeader, 1L);
        Map<String, Object> cart = cartService.loadCartSummary(userId);
        List<Map<String, Object>> addresses = addressRepository.listAddresses(userId);
        Map<String, Object> response = base();
        response.put("cart", cart);
        response.put("addresses", addresses);
        response.put("address_count", addresses.size());
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
