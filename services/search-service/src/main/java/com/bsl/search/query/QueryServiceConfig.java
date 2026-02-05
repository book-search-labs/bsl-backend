package com.bsl.search.query;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties(QueryServiceProperties.class)
public class QueryServiceConfig {
    @Bean
    public RestTemplate queryServiceRestTemplate(RestTemplateBuilder builder, QueryServiceProperties properties) {
        return builder
            .setConnectTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .build();
    }
}
