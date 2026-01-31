package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.ShipmentService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class ShipmentController {
    private final ShipmentService shipmentService;

    public ShipmentController(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @PostMapping("/shipments")
    public Map<String, Object> createShipment(@RequestBody ShipmentCreateRequest request) {
        if (request == null || request.orderId == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "order_id is required");
        }
        List<ShipmentService.ShipmentItemRequest> items = request.items == null ? null : request.items.stream()
            .map(item -> new ShipmentService.ShipmentItemRequest(item.orderItemId, item.skuId, item.qty))
            .toList();
        Map<String, Object> shipment = shipmentService.createShipment(request.orderId, items);
        long resolvedShipmentId = com.bsl.commerce.common.JdbcUtils.asLong(shipment.get("shipment_id"));
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("items", shipmentService.listShipmentItems(resolvedShipmentId));
        response.put("events", shipmentService.listShipmentEvents(resolvedShipmentId));
        return response;
    }

    @PostMapping("/shipments/{shipmentId}/tracking")
    public Map<String, Object> assignTracking(
        @PathVariable long shipmentId,
        @RequestBody TrackingRequest request
    ) {
        if (request == null || request.carrierCode == null || request.trackingNumber == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "carrier_code and tracking_number are required");
        }
        Map<String, Object> shipment = shipmentService.assignTracking(shipmentId, request.carrierCode,
            request.trackingNumber);
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("events", shipmentService.listShipmentEvents(shipmentId));
        return response;
    }

    @PostMapping("/shipments/{shipmentId}/mock/status")
    public Map<String, Object> mockStatus(
        @PathVariable long shipmentId,
        @RequestBody StatusRequest request
    ) {
        if (request == null || request.status == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "status is required");
        }
        Map<String, Object> shipment = shipmentService.mockStatus(shipmentId, request.status);
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("events", shipmentService.listShipmentEvents(shipmentId));
        return response;
    }

    @GetMapping("/shipments/{shipmentId}")
    public Map<String, Object> getShipment(@PathVariable long shipmentId) {
        Map<String, Object> shipment = shipmentService.getShipment(shipmentId);
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("items", shipmentService.listShipmentItems(shipmentId));
        response.put("events", shipmentService.listShipmentEvents(shipmentId));
        return response;
    }

    @GetMapping("/shipments/by-order/{orderId}")
    public Map<String, Object> listByOrder(@PathVariable long orderId) {
        List<Map<String, Object>> shipments = shipmentService.listShipmentsByOrder(orderId);
        Map<String, Object> response = base();
        response.put("items", shipments);
        response.put("count", shipments.size());
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

    public static class ShipmentCreateRequest {
        public Long orderId;
        public List<ShipmentItemRequest> items;
    }

    public static class ShipmentItemRequest {
        public long orderItemId;
        public Long skuId;
        public int qty;
    }

    public static class TrackingRequest {
        public String carrierCode;
        public String trackingNumber;
    }

    public static class StatusRequest {
        public String status;
    }
}
