package com.bsl.bff.config;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties({DownstreamProperties.class, OutboxProperties.class})
public class BffConfig {
    @Bean
    public RestTemplate queryServiceRestTemplate(RestTemplateBuilder builder, DownstreamProperties properties) {
        DownstreamProperties.ServiceProperties config = properties.getQueryService();
        return builder
            .setConnectTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .build();
    }

    @Bean
    public RestTemplate searchServiceRestTemplate(RestTemplateBuilder builder, DownstreamProperties properties) {
        DownstreamProperties.ServiceProperties config = properties.getSearchService();
        return builder
            .setConnectTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .build();
    }

    @Bean
    public RestTemplate autocompleteServiceRestTemplate(RestTemplateBuilder builder, DownstreamProperties properties) {
        DownstreamProperties.ServiceProperties config = properties.getAutocompleteService();
        return builder
            .setConnectTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(config.getTimeoutMs()))
            .build();
    }
}
