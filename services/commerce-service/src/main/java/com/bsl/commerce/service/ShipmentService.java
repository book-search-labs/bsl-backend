package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.common.JsonUtils;
import com.bsl.commerce.repository.OrderRepository;
import com.bsl.commerce.repository.ShipmentRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ShipmentService {
    private final ShipmentRepository shipmentRepository;
    private final OrderRepository orderRepository;
    private final OrderService orderService;
    private final ObjectMapper objectMapper;

    public ShipmentService(
        ShipmentRepository shipmentRepository,
        OrderRepository orderRepository,
        OrderService orderService,
        ObjectMapper objectMapper
    ) {
        this.shipmentRepository = shipmentRepository;
        this.orderRepository = orderRepository;
        this.orderService = orderService;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> createShipment(long orderId, List<ShipmentItemRequest> items) {
        Map<String, Object> order = orderRepository.findOrderById(orderId);
        if (order == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "order not found");
        }
        String status = JdbcUtils.asString(order.get("status"));
        if (!"PAID".equals(status) && !"READY_TO_SHIP".equals(status)) {
            throw new ApiException(HttpStatus.CONFLICT, "invalid_state", "order not ready for shipment");
        }

        long shipmentId = shipmentRepository.insertShipment(orderId, "READY");

        List<Map<String, Object>> orderItems = orderRepository.findOrderItems(orderId);
        List<ShipmentRepository.ShipmentItemInsert> inserts = new ArrayList<>();
        if (items == null || items.isEmpty()) {
            for (Map<String, Object> orderItem : orderItems) {
                inserts.add(new ShipmentRepository.ShipmentItemInsert(
                    shipmentId,
                    JdbcUtils.asLong(orderItem.get("order_item_id")),
                    JdbcUtils.asLong(orderItem.get("sku_id")),
                    JdbcUtils.asInt(orderItem.get("qty"))
                ));
            }
        } else {
            for (ShipmentItemRequest item : items) {
                inserts.add(new ShipmentRepository.ShipmentItemInsert(
                    shipmentId,
                    item.orderItemId(),
                    item.skuId(),
                    item.qty()
                ));
            }
        }
        shipmentRepository.insertShipmentItems(inserts);
        shipmentRepository.insertShipmentEvent(shipmentId, "SHIPMENT_CREATED", Timestamp.from(Instant.now()), null);

        if ("PAID".equals(status)) {
            orderService.markReadyToShip(orderId);
        }

        return shipmentRepository.findShipment(shipmentId);
    }

    @Transactional
    public Map<String, Object> assignTracking(long shipmentId, String carrier, String trackingNumber) {
        Map<String, Object> shipment = shipmentRepository.findShipment(shipmentId);
        if (shipment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "shipment not found");
        }
        shipmentRepository.updateTracking(
            shipmentId,
            carrier,
            trackingNumber,
            "SHIPPED",
            Timestamp.from(Instant.now())
        );
        shipmentRepository.insertShipmentEvent(
            shipmentId,
            "TRACKING_ASSIGNED",
            Timestamp.from(Instant.now()),
            null
        );
        long orderId = JdbcUtils.asLong(shipment.get("order_id"));
        try {
            orderService.markReadyToShip(orderId);
        } catch (ApiException ignored) {
            // ignore if already ready or moved ahead
        }
        orderService.markShipped(orderId);
        return shipmentRepository.findShipment(shipmentId);
    }

    @Transactional
    public Map<String, Object> mockStatus(long shipmentId, String status) {
        Map<String, Object> shipment = shipmentRepository.findShipment(shipmentId);
        if (shipment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "shipment not found");
        }
        Timestamp deliveredAt = null;
        if ("DELIVERED".equalsIgnoreCase(status)) {
            deliveredAt = Timestamp.from(Instant.now());
        }
        shipmentRepository.updateStatus(shipmentId, status, deliveredAt);
        shipmentRepository.insertShipmentEvent(
            shipmentId,
            "STATUS_UPDATED",
            Timestamp.from(Instant.now()),
            JsonUtils.toJson(objectMapper, Map.of("status", status))
        );
        long orderId = JdbcUtils.asLong(shipment.get("order_id"));
        if ("DELIVERED".equalsIgnoreCase(status)) {
            try {
                orderService.markReadyToShip(orderId);
            } catch (ApiException ignored) {
            }
            try {
                orderService.markShipped(orderId);
            } catch (ApiException ignored) {
            }
            orderService.markDelivered(orderId);
        }
        return shipmentRepository.findShipment(shipmentId);
    }

    public Map<String, Object> getShipment(long shipmentId) {
        Map<String, Object> shipment = shipmentRepository.findShipment(shipmentId);
        if (shipment == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "shipment not found");
        }
        return shipment;
    }

    public List<Map<String, Object>> listShipmentsByOrder(long orderId) {
        return shipmentRepository.listShipmentsByOrder(orderId);
    }

    public List<Map<String, Object>> listShipments(int limit) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return shipmentRepository.listShipments(resolved);
    }

    public List<Map<String, Object>> listShipmentItems(long shipmentId) {
        return shipmentRepository.listShipmentItems(shipmentId);
    }

    public List<Map<String, Object>> listShipmentEvents(long shipmentId) {
        return shipmentRepository.listShipmentEvents(shipmentId);
    }

    public record ShipmentItemRequest(long orderItemId, Long skuId, int qty) {
    }
}
