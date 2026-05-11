package com.bsl.checkoutorchestrator.config;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties(CheckoutOrchestratorProperties.class)
public class CheckoutOrchestratorConfig {
    @Bean
    public RestTemplate checkoutDownstreamRestTemplate(
        RestTemplateBuilder builder,
        CheckoutOrchestratorProperties properties
    ) {
        int timeoutMs = Math.max(
            Math.max(properties.getDownstream().getOrderService().getTimeoutMs(), properties.getDownstream().getPaymentService().getTimeoutMs()),
            Math.max(properties.getDownstream().getInventoryService().getTimeoutMs(), properties.getDownstream().getShipmentService().getTimeoutMs())
        );
        return builder
            .setConnectTimeout(Duration.ofMillis(timeoutMs))
            .setReadTimeout(Duration.ofMillis(timeoutMs))
            .build();
    }
}

