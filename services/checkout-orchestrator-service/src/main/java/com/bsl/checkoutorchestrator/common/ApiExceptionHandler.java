package com.bsl.checkoutorchestrator.common;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger logger = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorResponse> handleApiException(ApiException ex, HttpServletRequest request) {
        return ResponseEntity.status(ex.getStatus()).body(error(ex.getCode(), ex.getMessage(), request));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleInvalidJson(HttpServletRequest request) {
        return ResponseEntity.badRequest()
            .body(error("bad_request", "요청 본문 형식이 올바르지 않습니다.", request));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception ex, HttpServletRequest request) {
        logger.error(
            "unexpected_exception service=checkout-orchestrator-service request_id={} trace_id={} method={} path={}",
            requestId(request),
            traceId(request),
            request == null ? null : request.getMethod(),
            request == null ? null : request.getRequestURI(),
            ex
        );
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(error("internal_error", "서버 내부 오류가 발생했습니다.", request));
    }

    private ErrorResponse error(String code, String message, HttpServletRequest request) {
        return new ErrorResponse(new ErrorResponse.ErrorDetail(code, message), traceId(request), requestId(request));
    }

    private String traceId(HttpServletRequest request) {
        String value = request == null ? null : request.getHeader("x-trace-id");
        return value == null || value.isBlank() ? "unknown" : value;
    }

    private String requestId(HttpServletRequest request) {
        String value = request == null ? null : request.getHeader("x-request-id");
        return value == null || value.isBlank() ? "unknown" : value;
    }
}
