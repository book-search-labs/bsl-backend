package com.bsl.olaploader.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({OlapLoaderProperties.class, OlapTopicProperties.class})
public class OlapLoaderConfig {}
