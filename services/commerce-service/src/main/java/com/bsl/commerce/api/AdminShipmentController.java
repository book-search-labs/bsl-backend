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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin")
public class AdminShipmentController {
    private final ShipmentService shipmentService;

    public AdminShipmentController(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @GetMapping("/shipments")
    public Map<String, Object> listShipments(@RequestParam(name = "limit", required = false) Integer limit) {
        List<Map<String, Object>> shipments = shipmentService.listShipments(limit == null ? 50 : limit);
        Map<String, Object> response = base();
        response.put("items", shipments);
        response.put("count", shipments.size());
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

    @PostMapping("/shipments/{shipmentId}/label")
    public Map<String, Object> assignLabel(
        @PathVariable long shipmentId,
        @RequestBody TrackingRequest request
    ) {
        if (request == null || request.carrierCode == null || request.trackingNumber == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "carrier_code and tracking_number required");
        }
        Map<String, Object> shipment = shipmentService.assignTracking(shipmentId, request.carrierCode,
            request.trackingNumber);
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("events", shipmentService.listShipmentEvents(shipmentId));
        return response;
    }

    @PostMapping("/shipments/{shipmentId}/status")
    public Map<String, Object> updateStatus(@PathVariable long shipmentId, @RequestBody StatusRequest request) {
        if (request == null || request.status == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "status is required");
        }
        Map<String, Object> shipment = shipmentService.mockStatus(shipmentId, request.status);
        Map<String, Object> response = base();
        response.put("shipment", shipment);
        response.put("events", shipmentService.listShipmentEvents(shipmentId));
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

    public static class TrackingRequest {
        public String carrierCode;
        public String trackingNumber;
    }

    public static class StatusRequest {
        public String status;
    }
}
