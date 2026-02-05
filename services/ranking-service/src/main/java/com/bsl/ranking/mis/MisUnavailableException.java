package com.bsl.ranking.mis;

public class MisUnavailableException extends RuntimeException {
    public MisUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }

    public MisUnavailableException(String message) {
        super(message);
    }
}
