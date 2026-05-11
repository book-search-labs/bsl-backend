package com.bsl.checkoutorchestrator.domain;

public enum CheckoutStepStatus {
    READY,
    PROCESSING,
    SUCCEEDED,
    UNKNOWN,
    FAILED_RETRYING,
    MANUAL_REVIEW_REQUIRED,
    COMPENSATING,
    COMPENSATED,
    SKIPPED;

    public static boolean canTransition(CheckoutStepStatus from, CheckoutStepStatus to) {
        if (from == null) {
            return to == READY;
        }
        return switch (from) {
            case READY -> to == PROCESSING || to == SKIPPED;
            case PROCESSING -> to == SUCCEEDED || to == UNKNOWN || to == FAILED_RETRYING || to == MANUAL_REVIEW_REQUIRED;
            case UNKNOWN -> to == PROCESSING || to == SUCCEEDED || to == FAILED_RETRYING || to == MANUAL_REVIEW_REQUIRED;
            case FAILED_RETRYING -> to == READY || to == MANUAL_REVIEW_REQUIRED;
            case MANUAL_REVIEW_REQUIRED -> to == READY || to == PROCESSING;
            case SUCCEEDED -> to == COMPENSATING;
            case COMPENSATING -> to == COMPENSATED || to == MANUAL_REVIEW_REQUIRED;
            case COMPENSATED, SKIPPED -> false;
        };
    }
}

