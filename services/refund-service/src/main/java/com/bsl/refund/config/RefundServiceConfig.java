package com.bsl.refund.config;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties(RefundProperties.class)
public class RefundServiceConfig {
    @Bean
    public RestTemplate refundPaymentRestTemplate(RestTemplateBuilder builder, RefundProperties properties) {
        return restTemplate(builder, properties.getPaymentService());
    }

    @Bean
    public RestTemplate refundInventoryRestTemplate(RestTemplateBuilder builder, RefundProperties properties) {
        return restTemplate(builder, properties.getInventoryService());
    }

    private RestTemplate restTemplate(RestTemplateBuilder builder, RefundProperties.ServiceProperties properties) {
        return builder
            .setConnectTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .build();
    }
}
