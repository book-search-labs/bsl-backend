package com.bsl.commerce.common;

public final class PriceUtils {
    private static final int BOOK_PRICE_UNIT = 100;

    private PriceUtils() {
    }

    public static int normalizeBookPrice(int amount) {
        if (amount <= 0) {
            return 0;
        }
        return (amount / BOOK_PRICE_UNIT) * BOOK_PRICE_UNIT;
    }

    public static Integer normalizeBookPrice(Integer amount) {
        if (amount == null) {
            return null;
        }
        return normalizeBookPrice(amount.intValue());
    }
}
