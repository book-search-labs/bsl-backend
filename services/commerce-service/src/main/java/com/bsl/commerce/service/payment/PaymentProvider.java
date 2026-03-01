package com.bsl.commerce.service.payment;

import java.util.Locale;

public enum PaymentProvider {
    MOCK,
    LOCAL_SIM,
    TOSS,
    STRIPE;

    public static PaymentProvider from(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("payment provider is blank");
        }
        return PaymentProvider.valueOf(value.trim().toUpperCase(Locale.ROOT));
    }
}
