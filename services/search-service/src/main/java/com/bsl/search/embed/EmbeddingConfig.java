package com.bsl.search.embed;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties(EmbeddingProperties.class)
public class EmbeddingConfig {

    @Bean
    public RestTemplate embeddingRestTemplate(RestTemplateBuilder builder, EmbeddingProperties properties) {
        return builder
            .setConnectTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .setReadTimeout(Duration.ofMillis(properties.getTimeoutMs()))
            .build();
    }
}
