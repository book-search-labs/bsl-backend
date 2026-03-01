package com.bsl.bff.common;

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

    @ExceptionHandler(UnauthorizedException.class)
    public ResponseEntity<ErrorResponse> handleUnauthorized(UnauthorizedException ex) {
        RequestContext context = RequestContextHolder.get();
        ErrorResponse response = new ErrorResponse(
            "unauthorized",
            ex.getMessage(),
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(response);
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
        logger.error(
            "unexpected_exception request_id={} trace_id={} method={} path={}",
            context == null ? null : context.getRequestId(),
            context == null ? null : context.getTraceId(),
            request == null ? null : request.getMethod(),
            request == null ? null : request.getRequestURI(),
            ex
        );
        ErrorResponse response = new ErrorResponse(
            "internal_error",
            "서버 내부 오류가 발생했습니다.",
            context == null ? null : context.getTraceId(),
            context == null ? null : context.getRequestId()
        );
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(response);
    }
}
