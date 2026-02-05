package com.bsl.ranking.features;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.Yaml;

@Component
public class FeatureSpecLoader {
    private static final Logger log = LoggerFactory.getLogger(FeatureSpecLoader.class);

    public FeatureSpec load(String path) {
        Path resolved = resolvePath(path);
        if (!Files.exists(resolved)) {
            log.warn("feature spec not found at {}", path);
            return new FeatureSpec("v1", "fs_missing", List.of());
        }

        Map<String, Object> root;
        try (InputStream input = Files.newInputStream(resolved)) {
            Yaml yaml = new Yaml();
            Object parsed = yaml.load(input);
            if (!(parsed instanceof Map<?, ?> map)) {
                log.warn("feature spec malformed (root not map)");
                return new FeatureSpec("v1", "fs_invalid", List.of());
            }
            root = (Map<String, Object>) map;
        } catch (Exception ex) {
            log.warn("feature spec load failed", ex);
            return new FeatureSpec("v1", "fs_error", List.of());
        }

        String version = asString(root.get("version"), "v1");
        String featureSetVersion = asString(root.get("feature_set_version"), "fs_v1");
        List<FeatureDefinition> definitions = new ArrayList<>();
        Object rawFeatures = root.get("features");
        if (rawFeatures instanceof List<?> list) {
            for (Object item : list) {
                if (!(item instanceof Map<?, ?> map)) {
                    continue;
                }
                FeatureDefinition def = parseDefinition((Map<String, Object>) map);
                if (def != null) {
                    definitions.add(def);
                }
            }
        }
        return new FeatureSpec(version, featureSetVersion, definitions);
    }

    private Path resolvePath(String path) {
        Path direct = Path.of(path);
        if (Files.exists(direct) || direct.isAbsolute()) {
            return direct;
        }
        Path candidate = direct;
        for (int i = 0; i < 4; i++) {
            if (Files.exists(candidate)) {
                return candidate;
            }
            candidate = Path.of("..").resolve(candidate).normalize();
        }
        return direct;
    }

    private FeatureDefinition parseDefinition(Map<String, Object> map) {
        String name = asString(map.get("name"), null);
        FeatureType type = FeatureType.from(asString(map.get("type"), null));
        FeatureKeyType keyType = FeatureKeyType.from(asString(map.get("key_type"), null));
        FeatureSource source = FeatureSource.from(asString(map.get("source"), null));
        FeatureTransform transform = parseTransform(map.get("transform"));
        if (name == null || type == null || keyType == null || source == null) {
            return null;
        }
        return new FeatureDefinition(name, type, keyType, source, transform);
    }

    private FeatureTransform parseTransform(Object raw) {
        if (!(raw instanceof Map<?, ?> map)) {
            return new FeatureTransform(null, null, null, false, null);
        }
        Object defaultValue = map.get("default");
        Double clipMin = null;
        Double clipMax = null;
        boolean log1p = false;
        List<Double> bucketize = null;

        Object clipRaw = map.get("clip");
        if (clipRaw instanceof Map<?, ?> clipMap) {
            clipMin = asDouble(clipMap.get("min"));
            clipMax = asDouble(clipMap.get("max"));
        }

        Object logRaw = map.get("log1p");
        if (logRaw instanceof Boolean boolVal) {
            log1p = boolVal;
        }

        Object bucketRaw = map.get("bucketize");
        if (bucketRaw instanceof List<?> list) {
            bucketize = toDoubleList(list);
        } else if (bucketRaw instanceof Map<?, ?> bucketMap) {
            Object boundaries = bucketMap.get("boundaries");
            if (boundaries instanceof List<?> list) {
                bucketize = toDoubleList(list);
            }
        }

        return new FeatureTransform(defaultValue, clipMin, clipMax, log1p, bucketize);
    }

    private List<Double> toDoubleList(List<?> list) {
        List<Double> values = new ArrayList<>();
        for (Object entry : list) {
            Double val = asDouble(entry);
            if (val != null) {
                values.add(val);
            }
        }
        return values.isEmpty() ? null : values;
    }

    private String asString(Object raw, String fallback) {
        if (raw == null) {
            return fallback;
        }
        String value = raw.toString().trim();
        return value.isEmpty() ? fallback : value;
    }

    private Double asDouble(Object raw) {
        if (raw instanceof Number number) {
            return number.doubleValue();
        }
        if (raw instanceof String text) {
            try {
                return Double.parseDouble(text.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }
}
