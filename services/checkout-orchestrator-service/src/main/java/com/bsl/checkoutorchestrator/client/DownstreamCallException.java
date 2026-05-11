package com.bsl.checkoutorchestrator.client;

public class DownstreamCallException extends RuntimeException {
    private final String code;
    private final boolean unknownOutcome;
    private final boolean retryable;

    public DownstreamCallException(String code, String message, boolean unknownOutcome, boolean retryable) {
        super(message);
        this.code = code;
        this.unknownOutcome = unknownOutcome;
        this.retryable = retryable;
    }

    public String getCode() {
        return code;
    }

    public boolean isUnknownOutcome() {
        return unknownOutcome;
    }

    public boolean isRetryable() {
        return retryable;
    }
}

