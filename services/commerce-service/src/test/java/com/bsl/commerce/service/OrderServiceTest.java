package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.AddressRepository;
import com.bsl.commerce.repository.CartRepository;
import com.bsl.commerce.repository.OrderRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
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

    private OrderService newService() {
        CommerceProperties properties = new CommerceProperties();
        return new OrderService(
            orderRepository,
            cartRepository,
            catalogService,
            inventoryService,
            addressRepository,
            properties,
            objectMapper
        );
    }

    @Test
    void createOrderReturnsExistingWhenIdempotent() {
        OrderService service = newService();

        Map<String, Object> existing = Map.of("order_id", 99L);
        when(orderRepository.findOrderByIdempotencyKey("idem-1")).thenReturn(existing);

        Map<String, Object> result = service.createOrder(
            1L,
            null,
            List.of(new OrderService.OrderItemRequest(1L, 1L, 1, null, 100)),
            null,
            null,
            "STANDARD",
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
            any(),
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
        OrderService service = newService();

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
            "STANDARD",
            "CARD",
            "idem-2"
        ))
            .isInstanceOf(ApiException.class)
            .satisfies((error) -> {
                ApiException apiException = (ApiException) error;
                assertThat(apiException.getCode()).isEqualTo("price_changed");
            });
    }

    @Test
    void getOrderItemsEnrichesDisplayMetadata() {
        OrderService service = newService();

        Map<String, Object> row = new HashMap<>();
        row.put("order_item_id", 12L);
        row.put("sku_id", 43L);
        row.put("seller_id", 1L);
        row.put("qty", 1);
        row.put("unit_price", 33061);
        row.put("item_amount", 33061);
        row.put("price_snapshot_json", "{\"material_title\":\"초등영어교육의 영미문화지도에 관한 연구\"}");

        when(orderRepository.findOrderItems(99L)).thenReturn(List.of(row));
        when(catalogService.getSkuDisplayInfo(43L, 1L)).thenReturn(
            Map.of(
                "material_id", "nlk:CM000000001",
                "title", "초등영어교육의 영미문화지도에 관한 연구",
                "author", "홍길동",
                "publisher", "BSL 출판"
            )
        );

        List<Map<String, Object>> items = service.getOrderItems(99L);

        assertThat(items).hasSize(1);
        Map<String, Object> item = items.get(0);
        assertThat(item.get("title")).isEqualTo("초등영어교육의 영미문화지도에 관한 연구");
        assertThat(item.get("author")).isEqualTo("홍길동");
        assertThat(item.get("unit_price")).isEqualTo(33000);
        assertThat(item.get("item_amount")).isEqualTo(33000);
    }

    @Test
    void listOrdersIncludesPrimaryBookSummary() {
        OrderService service = newService();

        Map<String, Object> order = new HashMap<>();
        order.put("order_id", 7L);
        order.put("user_id", 1L);
        order.put("status", "PAID");
        order.put("total_amount", 33000);
        order.put("currency", "KRW");

        Map<String, Object> item = new HashMap<>();
        item.put("order_item_id", 21L);
        item.put("sku_id", 43L);
        item.put("seller_id", 1L);
        item.put("qty", 1);
        item.put("unit_price", 33000);
        item.put("item_amount", 33000);

        when(orderRepository.listOrdersByUser(1L, 20)).thenReturn(List.of(order));
        when(orderRepository.findOrderItems(7L)).thenReturn(List.of(item));
        when(catalogService.getSkuDisplayInfo(43L, 1L)).thenReturn(
            Map.of(
                "material_id", "nlk:CM000000001",
                "title", "초등영어교육의 영미문화지도에 관한 연구",
                "author", "홍길동"
            )
        );

        List<Map<String, Object>> orders = service.listOrders(1L, null);

        assertThat(orders).hasSize(1);
        Map<String, Object> mapped = orders.get(0);
        assertThat(mapped.get("item_count")).isEqualTo(1);
        assertThat(mapped.get("primary_item_title")).isEqualTo("초등영어교육의 영미문화지도에 관한 연구");
        assertThat(mapped.get("primary_item_author")).isEqualTo("홍길동");
        assertThat(mapped.get("primary_item_material_id")).isEqualTo("nlk:CM000000001");
    }

    @Test
    void markRefundPendingTransitionsFromReadyToShip() {
        OrderService service = newService();

        Map<String, Object> order = new HashMap<>();
        order.put("order_id", 88L);
        order.put("status", "READY_TO_SHIP");

        when(orderRepository.findOrderById(88L)).thenReturn(order);

        service.markRefundPending(88L);

        verify(orderRepository).updateOrderStatus(88L, "REFUND_PENDING");
        verify(orderRepository).insertOrderEvent(88L, "REFUND_REQUESTED", "READY_TO_SHIP", "REFUND_PENDING", null, null);
    }
}
