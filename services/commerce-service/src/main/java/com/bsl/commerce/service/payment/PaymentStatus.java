package com.bsl.commerce.service.payment;

import java.util.EnumSet;
import java.util.Locale;
import java.util.Set;

public enum PaymentStatus {
    READY,
    PROCESSING,
    AUTHORIZED,
    CAPTURED,
    FAILED,
    CANCELED,
    REFUNDED,
    INITIATED;

    public static PaymentStatus from(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("payment status is blank");
        }
        return PaymentStatus.valueOf(value.trim().toUpperCase(Locale.ROOT));
    }

    public boolean canTransitionTo(PaymentStatus target) {
        if (target == null) {
            return false;
        }
        if (this == target) {
            return true;
        }
        Set<PaymentStatus> allowed = switch (this) {
            case READY -> EnumSet.of(PROCESSING, CANCELED);
            case PROCESSING -> EnumSet.of(AUTHORIZED, CAPTURED, FAILED, CANCELED);
            case AUTHORIZED -> EnumSet.of(CAPTURED, FAILED, CANCELED);
            case INITIATED -> EnumSet.of(PROCESSING, AUTHORIZED, CAPTURED, FAILED, CANCELED);
            case CAPTURED -> EnumSet.of(REFUNDED);
            case FAILED, CANCELED, REFUNDED -> EnumSet.noneOf(PaymentStatus.class);
        };
        return allowed.contains(target);
    }

    public boolean isTerminal() {
        return this == CAPTURED || this == FAILED || this == CANCELED || this == REFUNDED;
    }
}
