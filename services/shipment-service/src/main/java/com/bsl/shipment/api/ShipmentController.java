package com.bsl.shipment.api;

import com.bsl.shipment.service.ShipmentService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(value = "/internal/shipments", produces = MediaType.APPLICATION_JSON_VALUE)
public class ShipmentController {
    private final ShipmentService shipmentService;

    public ShipmentController(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @PostMapping
    public Map<String, Object> create(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return shipmentService.create(request, idempotencyKey, traceId, requestId);
    }

    @PostMapping("/cancel")
    public Map<String, Object> cancel(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return shipmentService.cancel(request, idempotencyKey, traceId, requestId);
    }

    @GetMapping("/by-idempotency-key/{idempotencyKey}")
    public Map<String, Object> findByIdempotencyKey(@PathVariable String idempotencyKey) {
        return shipmentService.findByIdempotencyKey(idempotencyKey);
    }
}
