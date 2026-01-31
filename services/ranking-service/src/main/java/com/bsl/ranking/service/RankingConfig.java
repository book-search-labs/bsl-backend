package com.bsl.ranking.service;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(RerankGuardrailsProperties.class)
public class RankingConfig {}
