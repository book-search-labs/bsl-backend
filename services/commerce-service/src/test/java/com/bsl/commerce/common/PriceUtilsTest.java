package com.bsl.commerce.common;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class PriceUtilsTest {

    @Test
    void normalizeBookPriceRoundsDownToHundred() {
        assertThat(PriceUtils.normalizeBookPrice(33061)).isEqualTo(33000);
        assertThat(PriceUtils.normalizeBookPrice(32540)).isEqualTo(32500);
        assertThat(PriceUtils.normalizeBookPrice(100)).isEqualTo(100);
    }

    @Test
    void normalizeBookPriceHandlesNullAndNonPositive() {
        assertThat(PriceUtils.normalizeBookPrice((Integer) null)).isNull();
        assertThat(PriceUtils.normalizeBookPrice(0)).isEqualTo(0);
        assertThat(PriceUtils.normalizeBookPrice(-100)).isEqualTo(0);
    }
}
