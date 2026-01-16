package com.bsl.search.opensearch;

public class OpenSearchRequestException extends RuntimeException {
    public OpenSearchRequestException(String message, Throwable cause) {
        super(message, cause);
    }
}
