package com.bsl.autocomplete.opensearch;

public class OpenSearchUnavailableException extends RuntimeException {
    public OpenSearchUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
