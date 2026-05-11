package com.bsl.checkoutorchestrator.domain;

public enum OutboxStatus {
    READY,
    PROCESSING,
    SUCCEEDED,
    FAILED_RETRYING,
    DLQ
}

