package com.bsl.ranking.features;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({FeatureSpecProperties.class, FeatureStoreProperties.class})
public class FeatureConfig {}
