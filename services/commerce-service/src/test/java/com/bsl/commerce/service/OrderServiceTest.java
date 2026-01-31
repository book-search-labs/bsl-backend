package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.AddressRepository;
import com.bsl.commerce.repository.CartRepository;
import com.bsl.commerce.repository.OrderRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private CartRepository cartRepository;

    @Mock
    private CatalogService catalogService;

    @Mock
    private InventoryService inventoryService;

    @Mock
    private AddressRepository addressRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void createOrderReturnsExistingWhenIdempotent() {
        OrderService service = new OrderService(
            orderRepository,
            cartRepository,
            catalogService,
            inventoryService,
            addressRepository,
            objectMapper
        );

        Map<String, Object> existing = Map.of("order_id", 99L);
        when(orderRepository.findOrderByIdempotencyKey("idem-1")).thenReturn(existing);

        Map<String, Object> result = service.createOrder(
            1L,
            null,
            List.of(new OrderService.OrderItemRequest(1L, 1L, 1, null, 100)),
            null,
            null,
            "CARD",
            "idem-1"
        );

        verify(orderRepository, never()).insertOrder(
            anyLong(),
            any(),
            any(),
            anyInt(),
            any(),
            anyInt(),
            anyInt(),
            any(),
            any(),
            any(),
            any()
        );
        org.assertj.core.api.Assertions.assertThat(result).isEqualTo(existing);
    }

    @Test
    void createOrderThrowsOnPriceChange() {
        OrderService service = new OrderService(
            orderRepository,
            cartRepository,
            catalogService,
            inventoryService,
            addressRepository,
            objectMapper
        );

        when(orderRepository.findOrderByIdempotencyKey("idem-2")).thenReturn(null);
        when(catalogService.requireCurrentOfferBySkuId(1L)).thenReturn(
            Map.of(
                "offer_id", 2L,
                "effective_price", 120,
                "currency", "KRW",
                "seller_id", 1L
            )
        );

        assertThatThrownBy(() -> service.createOrder(
            1L,
            null,
            List.of(new OrderService.OrderItemRequest(1L, 1L, 1, 1L, 100)),
            null,
            null,
            "CARD",
            "idem-2"
        ))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("offer changed");
    }
}
