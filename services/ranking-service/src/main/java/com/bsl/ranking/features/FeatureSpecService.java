package com.bsl.ranking.features;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class FeatureSpecService {
    private static final Logger log = LoggerFactory.getLogger(FeatureSpecService.class);

    private final FeatureSpecLoader loader;
    private final FeatureSpecProperties properties;
    private FeatureSpec spec;

    public FeatureSpecService(FeatureSpecLoader loader, FeatureSpecProperties properties) {
        this.loader = loader;
        this.properties = properties;
    }

    @PostConstruct
    public void init() {
        FeatureSpec loaded = loader.load(properties.getPath());
        try {
            FeatureSpecValidator.validate(loaded);
            spec = loaded;
            log.info("feature spec loaded version={} feature_set={}", loaded.getVersion(), loaded.getFeatureSetVersion());
        } catch (IllegalStateException ex) {
            if (properties.isStrict()) {
                throw ex;
            }
            log.warn("feature spec validation failed: {}", ex.getMessage());
            spec = loaded;
        }
    }

    public FeatureSpec getSpec() {
        return spec;
    }
}
