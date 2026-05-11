package com.bsl.refund.client;

public class DownstreamCallException extends RuntimeException {
    private final boolean timeout;

    public DownstreamCallException(String message, boolean timeout) {
        super(message);
        this.timeout = timeout;
    }

    public boolean isTimeout() {
        return timeout;
    }
}
