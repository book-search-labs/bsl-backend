package com.bsl.search.retrieval;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(VectorSearchProperties.class)
public class VectorSearchConfig {
}
