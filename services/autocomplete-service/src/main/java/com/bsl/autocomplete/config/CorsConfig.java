package com.bsl.autocomplete.config;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

  @Value("${app.cors.allowed-origins:}")
  private String allowedOrigins;

  @Value("${app.cors.allowed-methods:GET,POST,OPTIONS}")
  private String allowedMethods;

  @Value("${app.cors.allowed-headers:*}")
  private String allowedHeaders;

  @Value("${app.cors.exposed-headers:x-trace-id,x-request-id}")
  private String exposedHeaders;

  @Value("${app.cors.allow-credentials:true}")
  private boolean allowCredentials;

  @Override
  public void addCorsMappings(CorsRegistry registry) {
    List<String> origins = Arrays.stream(allowedOrigins.split(","))
      .map(String::trim)
      .filter(s -> !s.isEmpty())
      .collect(Collectors.toList());

    registry.addMapping("/**")
      .allowedOrigins(origins.toArray(String[]::new))
      .allowedMethods(Arrays.stream(allowedMethods.split(",")).map(String::trim).toArray(String[]::new))
      .allowedHeaders(Arrays.stream(allowedHeaders.split(",")).map(String::trim).toArray(String[]::new))
      .exposedHeaders(Arrays.stream(exposedHeaders.split(",")).map(String::trim).toArray(String[]::new))
      .allowCredentials(allowCredentials)
      .maxAge(3600);
  }
}
