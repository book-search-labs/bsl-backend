package com.bsl.commerce.service.payment;

import com.bsl.commerce.common.ApiException;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class PaymentGatewayFactory {
    private final Map<PaymentProvider, PaymentGateway> gateways;

    public PaymentGatewayFactory(List<PaymentGateway> gateways) {
        EnumMap<PaymentProvider, PaymentGateway> index = new EnumMap<>(PaymentProvider.class);
        for (PaymentGateway gateway : gateways) {
            index.put(gateway.provider(), gateway);
        }
        this.gateways = Map.copyOf(index);
    }

    public PaymentGateway get(PaymentProvider provider) {
        PaymentGateway gateway = gateways.get(provider);
        if (gateway != null) {
            return gateway;
        }
        throw new ApiException(
            HttpStatus.NOT_IMPLEMENTED,
            "payment_provider_not_supported",
            "지원하지 않는 결제 제공자입니다: " + provider
        );
    }
}
