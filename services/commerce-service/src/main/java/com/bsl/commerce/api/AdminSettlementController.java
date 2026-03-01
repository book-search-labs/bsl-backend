package com.bsl.commerce.api;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.SettlementService;
import java.time.LocalDate;
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
@RequestMapping("/admin/settlements")
public class AdminSettlementController {
    private final SettlementService settlementService;

    public AdminSettlementController(SettlementService settlementService) {
        this.settlementService = settlementService;
    }

    @GetMapping("/cycles")
    public Map<String, Object> listCycles(
        @RequestParam(name = "limit", required = false) Integer limit,
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "from", required = false) String from,
        @RequestParam(name = "to", required = false) String to
    ) {
        List<Map<String, Object>> cycles = settlementService.listCycles(limit == null ? 50 : limit, status, from, to);
        Map<String, Object> response = base();
        response.put("items", cycles);
        response.put("count", cycles.size());
        return response;
    }

    @PostMapping("/cycles")
    public Map<String, Object> createCycle(@RequestBody CreateCycleRequest request) {
        if (request == null || request.startDate == null || request.endDate == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "start_date, end_date는 필수입니다.");
        }
        Map<String, Object> result = settlementService.createCycle(request.startDate, request.endDate);
        Map<String, Object> response = base();
        response.putAll(result);
        return response;
    }

    @GetMapping("/cycles/{cycleId}")
    public Map<String, Object> getCycle(@PathVariable long cycleId) {
        Map<String, Object> result = settlementService.getCycleDetail(cycleId);
        Map<String, Object> response = base();
        response.putAll(result);
        return response;
    }

    @GetMapping("/cycles/{cycleId}/lines")
    public Map<String, Object> listLines(@PathVariable long cycleId) {
        List<Map<String, Object>> lines = settlementService.listLines(cycleId);
        Map<String, Object> response = base();
        response.put("items", lines);
        response.put("count", lines.size());
        return response;
    }

    @GetMapping("/payouts")
    public Map<String, Object> listPayouts(
        @RequestParam(name = "limit", required = false) Integer limit,
        @RequestParam(name = "status", required = false) String status
    ) {
        List<Map<String, Object>> payouts = settlementService.listPayouts(limit == null ? 50 : limit, status);
        Map<String, Object> response = base();
        response.put("items", payouts);
        response.put("count", payouts.size());
        return response;
    }

    @GetMapping("/reconciliation")
    public Map<String, Object> listReconciliation(
        @RequestParam(name = "limit", required = false) Integer limit,
        @RequestParam(name = "from", required = false) String from,
        @RequestParam(name = "to", required = false) String to
    ) {
        Map<String, Object> result = settlementService.listReconciliationMismatches(limit == null ? 50 : limit, from, to);
        Map<String, Object> response = base();
        response.putAll(result);
        return response;
    }

    @PostMapping("/cycles/{cycleId}/payouts")
    public Map<String, Object> runPayouts(@PathVariable long cycleId) {
        Map<String, Object> result = settlementService.runPayouts(cycleId);
        Map<String, Object> response = base();
        response.putAll(result);
        return response;
    }

    @PostMapping("/payouts/{payoutId}/retry")
    public Map<String, Object> retryPayout(@PathVariable long payoutId) {
        Map<String, Object> result = settlementService.retryPayout(payoutId);
        Map<String, Object> response = base();
        response.putAll(result);
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

    public static class CreateCycleRequest {
        public LocalDate startDate;
        public LocalDate endDate;
    }
}
