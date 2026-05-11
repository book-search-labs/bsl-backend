package com.bsl.inventory.service;

import com.bsl.inventory.common.ApiException;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class FailureModeService {
    private static final long TIMEOUT_SLEEP_MS = 1_500L;
    private final AtomicReference<FailureMode> mode = new AtomicReference<>(FailureMode.SUCCESS);

    public Map<String, Object> setMode(String value) {
        FailureMode next = FailureMode.valueOf(value);
        mode.set(next);
        return Map.of("service", "inventory-service", "failure_mode", next.name());
    }

    public FailureMode beforeSideEffect() {
        FailureMode selected = selectedMode();
        if (selected == FailureMode.FAIL_500) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "failure_mode_500", "inventory failure mode FAIL_500");
        }
        if (selected == FailureMode.TIMEOUT) {
            sleep();
            throw new ApiException(HttpStatus.GATEWAY_TIMEOUT, "failure_mode_timeout", "inventory failure mode TIMEOUT");
        }
        return selected;
    }

    public void afterSideEffect(FailureMode selected) {
        if (selected == FailureMode.SUCCESS_BUT_TIMEOUT) {
            sleep();
        }
    }

    private FailureMode selectedMode() {
        FailureMode current = mode.get();
        if (current != FailureMode.RANDOM) {
            return current;
        }
        FailureMode[] values = {
            FailureMode.SUCCESS,
            FailureMode.FAIL_500,
            FailureMode.TIMEOUT,
            FailureMode.SUCCESS_BUT_TIMEOUT
        };
        return values[ThreadLocalRandom.current().nextInt(values.length)];
    }

    private void sleep() {
        try {
            Thread.sleep(TIMEOUT_SLEEP_MS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "failure_mode_interrupted", "failure mode sleep interrupted");
        }
    }
}

