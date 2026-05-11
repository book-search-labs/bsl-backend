package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.OrderRepository;
import io.micrometer.core.instrument.Metrics;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderExpirationScheduler {
    private static final Logger logger = LoggerFactory.getLogger(OrderExpirationScheduler.class);

    private final OrderRepository orderRepository;
    private final OrderService orderService;
    private final boolean enabled;
    private final int batchSize;

    public OrderExpirationScheduler(
        OrderRepository orderRepository,
        OrderService orderService,
        @Value("${orders.expiration-enabled:true}") boolean enabled,
        @Value("${orders.expiration-batch-size:100}") int batchSize
    ) {
        this.orderRepository = orderRepository;
        this.orderService = orderService;
        this.enabled = enabled;
        this.batchSize = Math.max(1, Math.min(batchSize, 500));
    }

    @Scheduled(
        fixedDelayString = "${orders.expiration-delay-ms:30000}",
        initialDelayString = "${orders.expiration-initial-delay-ms:15000}"
    )
    public void expireDueOrders() {
        if (!enabled) {
            return;
        }

        List<Long> orderIds = orderRepository.findExpirableOrderIds(batchSize);
        if (orderIds.isEmpty()) {
            return;
        }

        int expired = 0;
        int skipped = 0;
        int failed = 0;
        for (Long orderId : orderIds) {
            try {
                if (orderService.expireOrder(orderId)) {
                    expired++;
                } else {
                    skipped++;
                }
            } catch (ApiException ex) {
                failed++;
                logger.warn("order_expiration_failed order_id={} code={}", orderId, ex.getCode());
            } catch (Exception ex) {
                failed++;
                logger.warn("order_expiration_error order_id={} message={}", orderId, ex.getMessage());
            }
        }

        Metrics.counter("commerce.order.expiration.total", "outcome", "expired").increment(expired);
        Metrics.counter("commerce.order.expiration.total", "outcome", "skipped").increment(skipped);
        Metrics.counter("commerce.order.expiration.total", "outcome", "failed").increment(failed);
        logger.info(
            "order_expiration_batch candidates={} expired={} skipped={} failed={}",
            orderIds.size(),
            expired,
            skipped,
            failed
        );
    }
}
