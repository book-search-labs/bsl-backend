package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.OpsTaskRepository;
import com.bsl.commerce.repository.PaymentRepository;
import com.bsl.commerce.repository.RefundRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RefundServiceTest {

    @Mock
    private RefundRepository refundRepository;

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentRepository paymentRepository;

    @Mock
    private InventoryService inventoryService;

    @Mock
    private OrderService orderService;

    @Mock
    private OpsTaskRepository opsTaskRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private RefundService newService() {
        CommerceProperties properties = new CommerceProperties();
        properties.getCart().setBaseShippingFee(3000);
        properties.getCart().setFastShippingFee(5000);
        return new RefundService(
            refundRepository,
            orderRepository,
            paymentRepository,
            inventoryService,
            orderService,
            opsTaskRepository,
            properties,
            objectMapper
        );
    }

    @Test
    void createRefundPreShipmentFullRefundIncludesShipping() {
        RefundService service = newService();

        Map<String, Object> order = new HashMap<>();
        order.put("order_id", 1L);
        order.put("status", "PAID");
        order.put("shipping_fee", 3000);
        order.put("shipping_mode", "STANDARD");

        Map<String, Object> payment = Map.of("payment_id", 11L);

        Map<String, Object> orderItem = new HashMap<>();
        orderItem.put("order_item_id", 101L);
        orderItem.put("sku_id", 43L);
        orderItem.put("qty", 1);
        orderItem.put("unit_price", 33000);

        when(orderRepository.findOrderById(1L)).thenReturn(order);
        when(refundRepository.findRefundByIdempotencyKey("idem-pre")).thenReturn(null);
        when(paymentRepository.findLatestPaymentByOrder(1L)).thenReturn(payment);
        when(orderRepository.findOrderItems(1L)).thenReturn(List.of(orderItem));
        when(refundRepository.sumRefundedQtyByOrder(1L)).thenReturn(List.of());
        when(refundRepository.sumRefundAmountsByOrder(1L)).thenReturn(Map.of("shipping_refund_amount", 0));
        when(refundRepository.insertRefund(anyLong(), any(), any(), any(), any(), anyInt(), anyInt(), anyInt(), anyInt(), any(), any()))
            .thenReturn(501L);
        when(refundRepository.findRefund(501L)).thenReturn(Map.of("refund_id", 501L, "amount", 36000));

        Map<String, Object> result = service.createRefund(1L, null, "CHANGE_OF_MIND", null, "idem-pre");

        assertThat(result).containsEntry("refund_id", 501L);
        assertThat(result).containsEntry("amount", 36000);
        verify(refundRepository).insertRefund(
            eq(1L),
            eq(11L),
            eq("REQUESTED"),
            eq("CHANGE_OF_MIND"),
            isNull(),
            eq(33000),
            eq(3000),
            eq(0),
            eq(36000),
            eq("PRE_SHIPMENT_FULL_REFUND"),
            eq("idem-pre")
        );
        verify(refundRepository).insertRefundItems(any());
        verify(refundRepository).insertRefundEvent(eq(501L), eq("REFUND_REQUESTED"), any());
    }

    @Test
    void createRefundDeliveredChangeOfMindAppliesReturnFee() {
        RefundService service = newService();

        Map<String, Object> order = new HashMap<>();
        order.put("order_id", 2L);
        order.put("status", "DELIVERED");
        order.put("shipping_fee", 3000);
        order.put("shipping_mode", "STANDARD");

        Map<String, Object> payment = Map.of("payment_id", 22L);

        Map<String, Object> orderItem = new HashMap<>();
        orderItem.put("order_item_id", 202L);
        orderItem.put("sku_id", 55L);
        orderItem.put("qty", 1);
        orderItem.put("unit_price", 33000);

        when(orderRepository.findOrderById(2L)).thenReturn(order);
        when(refundRepository.findRefundByIdempotencyKey("idem-delivered")).thenReturn(null);
        when(paymentRepository.findLatestPaymentByOrder(2L)).thenReturn(payment);
        when(orderRepository.findOrderItems(2L)).thenReturn(List.of(orderItem));
        when(refundRepository.sumRefundedQtyByOrder(2L)).thenReturn(List.of());
        when(refundRepository.sumRefundAmountsByOrder(2L)).thenReturn(Map.of("shipping_refund_amount", 0));
        when(refundRepository.insertRefund(anyLong(), any(), any(), any(), any(), anyInt(), anyInt(), anyInt(), anyInt(), any(), any()))
            .thenReturn(502L);
        when(refundRepository.findRefund(502L)).thenReturn(Map.of("refund_id", 502L, "amount", 30000));

        Map<String, Object> result = service.createRefund(2L, null, "change_of_mind", "단순 변심", "idem-delivered");

        assertThat(result).containsEntry("refund_id", 502L);
        assertThat(result).containsEntry("amount", 30000);
        verify(refundRepository).insertRefund(
            eq(2L),
            eq(22L),
            eq("REQUESTED"),
            eq("CHANGE_OF_MIND"),
            eq("단순 변심"),
            eq(33000),
            eq(0),
            eq(3000),
            eq(30000),
            eq("CUSTOMER_REMORSE_RETURN"),
            eq("idem-delivered")
        );
        verify(refundRepository).insertRefundItems(any());
        verify(refundRepository).insertRefundEvent(eq(502L), eq("REFUND_REQUESTED"), any());
    }
}
