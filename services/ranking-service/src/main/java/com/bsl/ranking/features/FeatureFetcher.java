package com.bsl.ranking.features;

import com.bsl.ranking.api.dto.RerankRequest;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class FeatureFetcher {
    private final FeatureSpecService specService;
    private final FeatureStoreClient featureStore;

    public FeatureFetcher(FeatureSpecService specService, FeatureStoreClient featureStore) {
        this.specService = specService;
        this.featureStore = featureStore;
    }

    public List<EnrichedCandidate> enrich(List<RerankRequest.Candidate> candidates, String queryText) {
        FeatureSpec spec = specService.getSpec();
        List<String> docIds = new ArrayList<>();
        for (RerankRequest.Candidate candidate : candidates) {
            if (candidate != null && candidate.getDocId() != null) {
                docIds.add(candidate.getDocId());
            }
        }
        Map<String, Map<String, Object>> storeValues = featureStore.fetch(docIds);
        List<EnrichedCandidate> enriched = new ArrayList<>();

        for (RerankRequest.Candidate candidate : candidates) {
            if (candidate == null || candidate.getDocId() == null) {
                continue;
            }
            Map<String, Object> raw = new LinkedHashMap<>();
            Map<String, Double> transformed = new LinkedHashMap<>();
            List<String> reasons = new ArrayList<>();

            Map<String, Object> kv = storeValues.get(candidate.getDocId());
            for (FeatureDefinition def : spec.getFeatures()) {
                Object rawValue = resolveRaw(def, candidate, queryText, kv);
                raw.put(def.getName(), rawValue);
                transformed.put(def.getName(), applyTransform(def, rawValue));
            }

            enriched.add(new EnrichedCandidate(candidate.getDocId(), candidate, raw, transformed, reasons));
        }
        return enriched;
    }

    private Object resolveRaw(
        FeatureDefinition def,
        RerankRequest.Candidate candidate,
        String queryText,
        Map<String, Object> kv
    ) {
        return switch (def.getSource()) {
            case REQUEST -> resolveRequest(def.getName(), candidate);
            case KV -> kv == null ? null : kv.get(def.getName());
            case DERIVED -> resolveDerived(def.getName(), candidate, queryText, kv);
        };
    }

    private Object resolveRequest(String name, RerankRequest.Candidate candidate) {
        RerankRequest.Features features = candidate.getFeatures();
        if (features == null) {
            return null;
        }
        return switch (name) {
            case "lex_rank" -> features.getLexRank();
            case "vec_rank" -> features.getVecRank();
            case "rrf_score" -> features.getRrfScore();
            case "issued_year" -> features.getIssuedYear();
            case "volume" -> features.getVolume();
            case "edition_labels" -> features.getEditionLabels();
            default -> null;
        };
    }

    private Object resolveDerived(
        String name,
        RerankRequest.Candidate candidate,
        String queryText,
        Map<String, Object> kv
    ) {
        return switch (name) {
            case "has_recover" -> hasRecover(candidate);
            case "freshness_days" -> computeFreshnessDays(candidate, kv);
            case "query_len" -> queryText == null ? 0 : queryText.trim().length();
            default -> null;
        };
    }

    private boolean hasRecover(RerankRequest.Candidate candidate) {
        RerankRequest.Features features = candidate.getFeatures();
        if (features == null || features.getEditionLabels() == null) {
            return false;
        }
        for (String label : features.getEditionLabels()) {
            if (label != null && label.equalsIgnoreCase("recover")) {
                return true;
            }
        }
        return false;
    }

    private Integer computeFreshnessDays(RerankRequest.Candidate candidate, Map<String, Object> kv) {
        Integer issuedYear = null;
        if (candidate.getFeatures() != null && candidate.getFeatures().getIssuedYear() != null) {
            issuedYear = candidate.getFeatures().getIssuedYear();
        }
        if (issuedYear == null && kv != null) {
            Object raw = kv.get("issued_year");
            if (raw instanceof Number number) {
                issuedYear = number.intValue();
            } else if (raw instanceof String text) {
                try {
                    issuedYear = Integer.parseInt(text.trim());
                } catch (NumberFormatException ignored) {
                    issuedYear = null;
                }
            }
        }
        if (issuedYear == null) {
            return null;
        }
        int currentYear = LocalDate.now().getYear();
        int ageYears = Math.max(0, currentYear - issuedYear);
        return ageYears * 365;
    }

    private double applyTransform(FeatureDefinition def, Object rawValue) {
        FeatureTransform transform = def.getTransform();
        Object value = rawValue;
        if (value == null && transform != null) {
            value = transform.getDefaultValue();
        }
        if (value == null) {
            value = defaultForType(def.getType());
        }

        double numeric = toDouble(def.getType(), value);
        if (transform != null) {
            if (transform.isLog1p()) {
                numeric = Math.log1p(Math.max(0.0, numeric));
            }
            if (transform.getClipMin() != null) {
                numeric = Math.max(transform.getClipMin(), numeric);
            }
            if (transform.getClipMax() != null) {
                numeric = Math.min(transform.getClipMax(), numeric);
            }
            if (transform.getBucketize() != null && !transform.getBucketize().isEmpty()) {
                numeric = bucketize(numeric, transform.getBucketize());
            }
        }
        return numeric;
    }

    private double bucketize(double value, List<Double> boundaries) {
        int bucket = 0;
        for (Double boundary : boundaries) {
            if (boundary == null) {
                continue;
            }
            if (value <= boundary) {
                return bucket;
            }
            bucket++;
        }
        return bucket;
    }

    private Object defaultForType(FeatureType type) {
        if (type == FeatureType.BOOL) {
            return false;
        }
        return 0.0;
    }

    private double toDouble(FeatureType type, Object value) {
        if (value instanceof Boolean boolVal) {
            return boolVal ? 1.0 : 0.0;
        }
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        if (value instanceof String text) {
            try {
                return Double.parseDouble(text.trim());
            } catch (NumberFormatException ignored) {
                return 0.0;
            }
        }
        return type == FeatureType.BOOL ? 0.0 : 0.0;
    }
}
