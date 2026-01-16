package com.bsl.ranking.api;

import com.bsl.ranking.api.dto.ErrorResponse;
import com.bsl.ranking.api.dto.RerankRequest;
import com.bsl.ranking.api.dto.RerankResponse;
import com.bsl.ranking.service.ToyRerankService;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RerankController {
    private final ToyRerankService rerankService;

    public RerankController(ToyRerankService rerankService) {
        this.rerankService = rerankService;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @PostMapping("/rerank")
    public ResponseEntity<?> rerank(
        @RequestBody(required = false) RerankRequest request,
        @RequestHeader(value = "x-trace-id", required = false) String traceHeader,
        @RequestHeader(value = "x-request-id", required = false) String requestHeader
    ) {
        String traceId = RequestIdUtil.resolveOrGenerate(traceHeader);
        String requestId = RequestIdUtil.resolveOrGenerate(requestHeader);

        if (request == null || request.getQuery() == null || isBlank(request.getQuery().getText())) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "query.text is required", traceId, requestId)
            );
        }

        if (request.getCandidates() == null || request.getCandidates().isEmpty()) {
            return ResponseEntity.badRequest().body(
                new ErrorResponse("bad_request", "candidates is required", traceId, requestId)
            );
        }

        RerankResponse response = rerankService.rerank(request, traceId, requestId);
        return ResponseEntity.ok(response);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
