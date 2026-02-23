package com.bsl.bff.common;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(BadRequestException.class)
    public ResponseEntity<ErrorResponse> handleBadRequest(BadRequestException ex) {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse response = new ErrorResponse(
            "bad_request",
            ex.getMessage(),
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(DownstreamException.class)
    public ResponseEntity<ErrorResponse> handleDownstream(DownstreamException ex) {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse response = new ErrorResponse(
            ex.getCode(),
            ex.getMessage(),
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.status(ex.getStatus()).body(response);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleInvalidJson(HttpMessageNotReadableException ex) {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse response = new ErrorResponse(
            "bad_request",
            "요청 본문 형식이 올바르지 않습니다.",
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception ex, HttpServletRequest request) {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse response = new ErrorResponse(
            "internal_error",
            "서버 내부 오류가 발생했습니다.",
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(response);
    }
}
