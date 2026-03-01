package com.bsl.commerce.service.payment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bsl.commerce.common.ApiException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class PaymentGatewayFactoryTest {

    @Test
    void returnsGatewayByProvider() {
        PaymentGatewayFactory factory = new PaymentGatewayFactory(List.of(new MockPaymentGateway(), new LocalSimPaymentGateway()));

        PaymentGateway gateway = factory.get(PaymentProvider.MOCK);
        PaymentGateway local = factory.get(PaymentProvider.LOCAL_SIM);

        assertThat(gateway).isInstanceOf(MockPaymentGateway.class);
        assertThat(local).isInstanceOf(LocalSimPaymentGateway.class);
    }

    @Test
    void throwsWhenProviderGatewayIsMissing() {
        PaymentGatewayFactory factory = new PaymentGatewayFactory(List.of());

        assertThatThrownBy(() -> factory.get(PaymentProvider.MOCK))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> {
                ApiException ex = (ApiException) error;
                assertThat(ex.getStatus()).isEqualTo(HttpStatus.NOT_IMPLEMENTED);
                assertThat(ex.getCode()).isEqualTo("payment_provider_not_supported");
            });
    }
}
