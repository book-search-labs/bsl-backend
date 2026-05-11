package com.bsl.inventory.api;

import com.bsl.inventory.service.InventoryService;
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
@RequestMapping(value = "/internal/inventory", produces = MediaType.APPLICATION_JSON_VALUE)
public class InventoryController {
    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @PostMapping("/reserve")
    public Map<String, Object> reserve(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return inventoryService.reserve(request, idempotencyKey, traceId, requestId);
    }

    @PostMapping("/release")
    public Map<String, Object> release(
        @RequestBody(required = false) Map<String, Object> request,
        @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestHeader(value = "x-trace-id", required = false) String traceId,
        @RequestHeader(value = "x-request-id", required = false) String requestId
    ) {
        return inventoryService.release(request, idempotencyKey, traceId, requestId);
    }

    @GetMapping("/reservations/by-idempotency-key/{idempotencyKey}")
    public Map<String, Object> findByIdempotencyKey(@PathVariable String idempotencyKey) {
        return inventoryService.findByIdempotencyKey(idempotencyKey);
    }
}
