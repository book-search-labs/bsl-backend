package com.bsl.payment.api;

import com.bsl.payment.service.FailureModeService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class FailureModeController {
    private final FailureModeService failureModeService;

    public FailureModeController(FailureModeService failureModeService) {
        this.failureModeService = failureModeService;
    }

    @PostMapping("/internal/admin/failure-mode")
    public Map<String, Object> setFailureMode(@RequestBody Map<String, Object> request) {
        return failureModeService.setMode(request.getOrDefault("mode", "SUCCESS").toString());
    }
}

