package com.bsl.inventory.common;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApiException(ApiException ex, HttpServletRequest request) {
        return ResponseEntity.status(ex.getStatus()).body(error(ex.getCode(), ex.getMessage(), request));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleInvalidJson(HttpServletRequest request) {
        return ResponseEntity.badRequest().body(error("bad_request", "요청 본문 형식이 올바르지 않습니다.", request));
    }

    private ErrorResponse error(String code, String message, HttpServletRequest request) {
        return new ErrorResponse(new ErrorResponse.ErrorDetail(code, message), header(request, "x-trace-id"), header(request, "x-request-id"));
    }

    private String header(HttpServletRequest request, String name) {
        String value = request == null ? null : request.getHeader(name);
        return value == null || value.isBlank() ? "unknown" : value;
    }
}

