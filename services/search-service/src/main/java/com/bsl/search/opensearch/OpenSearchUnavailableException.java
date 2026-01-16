package com.bsl.search.opensearch;

public class OpenSearchUnavailableException extends RuntimeException {
    public OpenSearchUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
