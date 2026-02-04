package com.bsl.ranking.features;

import com.bsl.ranking.api.dto.RerankRequest;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class FeatureFetcher {
    private static final Pattern NUMBER_TOKEN_PATTERN = Pattern.compile(".*\\d+.*");
    private static final Pattern ISBN_PATTERN = Pattern.compile("^(97(8|9))?\\d{9}[\\dXx]$");
    private static final Pattern VOLUME_PATTERN = Pattern.compile("(?i)(\\bvol\\.?\\s*\\d+\\b|\\d+\\s*(권|편|부|집)|제\\s*\\d+\\s*권)");

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
                if (rawValue == null) {
                    String reason = "feature_missing:" + def.getName();
                    if (!reasons.contains(reason)) {
                        reasons.add(reason);
                    }
                }
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
            case "fused_rank" -> features.getFusedRank() != null ? features.getFusedRank() : features.getRrfRank();
            case "rrf_rank" -> features.getRrfRank() != null ? features.getRrfRank() : features.getFusedRank();
            case "bm25_score" -> features.getBm25Score();
            case "vec_score" -> features.getVecScore();
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
            case "query_len" -> queryLength(queryText);
            case "has_number_token" -> hasNumberToken(queryText);
            case "is_isbn_like" -> isIsbnLike(queryText);
            case "has_volume_like" -> hasVolumeLike(queryText);
            case "title_exact_match" -> exactMatch(queryText, candidate.getTitle());
            case "author_exact_match" -> authorExactMatch(queryText, candidate.getAuthors());
            case "series_exact_match" -> exactMatch(queryText, candidate.getSeries());
            case "metadata_completeness" -> metadataCompleteness(candidate, kv);
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

    private Integer queryLength(String queryText) {
        if (queryText == null) {
            return 0;
        }
        String trimmed = queryText.trim();
        if (trimmed.isEmpty()) {
            return 0;
        }
        return trimmed.length();
    }

    private boolean hasNumberToken(String queryText) {
        if (queryText == null || queryText.isBlank()) {
            return false;
        }
        return NUMBER_TOKEN_PATTERN.matcher(queryText).matches();
    }

    private boolean isIsbnLike(String queryText) {
        if (queryText == null || queryText.isBlank()) {
            return false;
        }
        String compact = queryText.replaceAll("[^0-9Xx]", "");
        return ISBN_PATTERN.matcher(compact).matches();
    }

    private boolean hasVolumeLike(String queryText) {
        if (queryText == null || queryText.isBlank()) {
            return false;
        }
        return VOLUME_PATTERN.matcher(queryText).find();
    }

    private boolean exactMatch(String queryText, String candidateText) {
        String normalizedQuery = normalizeText(queryText);
        String normalizedCandidate = normalizeText(candidateText);
        if (normalizedQuery == null || normalizedCandidate == null) {
            return false;
        }
        return normalizedQuery.equals(normalizedCandidate);
    }

    private boolean authorExactMatch(String queryText, List<String> authors) {
        String normalizedQuery = normalizeText(queryText);
        if (normalizedQuery == null || authors == null || authors.isEmpty()) {
            return false;
        }
        for (String author : authors) {
            String normalizedAuthor = normalizeText(author);
            if (normalizedAuthor != null && normalizedAuthor.equals(normalizedQuery)) {
                return true;
            }
        }
        return false;
    }

    private Double metadataCompleteness(RerankRequest.Candidate candidate, Map<String, Object> kv) {
        double score = 0.0;
        if (candidate.getAuthors() != null && !candidate.getAuthors().isEmpty()) {
            score += 0.4;
        }
        if (candidate.getPublisher() != null && !candidate.getPublisher().isBlank()) {
            score += 0.3;
        }
        Integer issuedYear = candidate.getFeatures() == null ? null : candidate.getFeatures().getIssuedYear();
        if (issuedYear == null && kv != null) {
            Object raw = kv.get("issued_year");
            if (raw instanceof Number number) {
                issuedYear = number.intValue();
            }
        }
        if (issuedYear != null && issuedYear > 0) {
            score += 0.3;
        }
        return score;
    }

    private String normalizeText(String text) {
        if (text == null) {
            return null;
        }
        String normalized = text.trim().toLowerCase();
        if (normalized.isEmpty()) {
            return null;
        }
        normalized = normalized.replaceAll("\\s+", " ");
        normalized = normalized.replaceAll("[\\p{Punct}]", "");
        normalized = normalized.replace(" ", "");
        return normalized.isEmpty() ? null : normalized;
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
