package com.bsl.commerce.service;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.repository.OrderRepository;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderExpirationSchedulerTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private OrderService orderService;

    @Test
    void skipsWhenDisabled() {
        OrderExpirationScheduler scheduler = new OrderExpirationScheduler(orderRepository, orderService, false, 100);

        scheduler.expireDueOrders();

        verify(orderRepository, never()).findExpirableOrderIds(100);
    }

    @Test
    void expiresDueOrdersByCallingServiceProxy() {
        OrderExpirationScheduler scheduler = new OrderExpirationScheduler(orderRepository, orderService, true, 100);
        when(orderRepository.findExpirableOrderIds(100)).thenReturn(List.of(11L, 12L));
        when(orderService.expireOrder(11L)).thenReturn(true);
        when(orderService.expireOrder(12L)).thenReturn(false);

        scheduler.expireDueOrders();

        verify(orderService).expireOrder(11L);
        verify(orderService).expireOrder(12L);
    }
}
