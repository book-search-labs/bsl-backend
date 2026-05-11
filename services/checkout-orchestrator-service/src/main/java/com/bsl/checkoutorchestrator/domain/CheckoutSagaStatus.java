package com.bsl.checkoutorchestrator.domain;

public enum CheckoutSagaStatus {
    PENDING,
    PROCESSING,
    SUCCEEDED,
    FAILED_RETRYING,
    MANUAL_REVIEW_REQUIRED,
    CANCELLING,
    CANCELLED,
    CANCEL_FAILED;

    public static boolean canTransition(CheckoutSagaStatus from, CheckoutSagaStatus to) {
        if (from == null) {
            return to == PENDING;
        }
        return switch (from) {
            case PENDING -> to == PROCESSING || to == CANCELLING;
            case PROCESSING -> to == SUCCEEDED
                || to == FAILED_RETRYING
                || to == MANUAL_REVIEW_REQUIRED
                || to == CANCELLING;
            case FAILED_RETRYING, MANUAL_REVIEW_REQUIRED -> to == PROCESSING || to == CANCELLING;
            case CANCELLING -> to == CANCELLED || to == CANCEL_FAILED;
            case CANCEL_FAILED -> to == CANCELLING;
            case SUCCEEDED -> to == CANCELLING;
            case CANCELLED -> false;
        };
    }
}

