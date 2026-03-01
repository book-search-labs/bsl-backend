package com.bsl.search.service.grouping;

import com.bsl.search.api.dto.BookHit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class MaterialGroupingService {
    private final MaterialGroupingProperties properties;

    public MaterialGroupingService(MaterialGroupingProperties properties) {
        this.properties = properties;
    }

    public List<BookHit> apply(String queryText, List<BookHit> hits, int size) {
        if (hits == null || hits.isEmpty()) {
            return hits;
        }
        if (properties == null || !properties.isEnabled()) {
            return hits;
        }

        Map<String, Group> groups = new LinkedHashMap<>();
        for (int i = 0; i < hits.size(); i++) {
            BookHit hit = hits.get(i);
            if (hit == null) {
                continue;
            }
            String key = groupKey(hit);
            groups.computeIfAbsent(key, k -> new Group()).add(hit, i);
        }

        List<BookHit> canonical = new ArrayList<>();
        List<GroupEntry> overflow = new ArrayList<>();
        for (Group group : groups.values()) {
            GroupEntry best = group.pickBest(queryText, properties);
            if (best != null) {
                canonical.add(best.hit());
            }
            overflow.addAll(group.others(best));
        }

        List<BookHit> combined = new ArrayList<>(canonical);
        if (size > 0 && combined.size() > size) {
            combined = new ArrayList<>(combined.subList(0, size));
        }
        if (properties.isFillVariants() && combined.size() < size) {
            overflow.sort(Comparator.comparingInt(GroupEntry::order));
            for (GroupEntry entry : overflow) {
                if (combined.size() >= size) {
                    break;
                }
                combined.add(entry.hit());
            }
        }

        for (int i = 0; i < combined.size(); i++) {
            combined.get(i).setRank(i + 1);
        }
        return combined;
    }

    private String groupKey(BookHit hit) {
        BookHit.Source source = hit.getSource();
        if (source == null) {
            return hit.getDocId();
        }
        String title = normalizeTitle(source.getTitleKo());
        String author = normalizeAuthor(source.getAuthors());
        Integer volume = source.getVolume();
        String volumeKey = volume == null || volume <= 0 ? "" : String.valueOf(volume);
        String base = String.join("|", title, author, volumeKey);
        return base.isBlank() ? hit.getDocId() : base;
    }

    private String normalizeTitle(String title) {
        if (title == null) {
            return "";
        }
        String normalized = title.trim().toLowerCase(Locale.ROOT);
        for (String token : defaultTokens(properties.getTitleStripTokens(), defaultStripTokens())) {
            if (!token.isBlank()) {
                normalized = normalized.replace(token.toLowerCase(Locale.ROOT), "");
            }
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < normalized.length(); i++) {
            char ch = normalized.charAt(i);
            if (Character.isLetterOrDigit(ch)) {
                sb.append(ch);
            }
        }
        return sb.toString();
    }

    private String normalizeAuthor(List<String> authors) {
        if (authors == null || authors.isEmpty()) {
            return "";
        }
        String first = authors.get(0);
        if (first == null) {
            return "";
        }
        return first.trim().toLowerCase(Locale.ROOT);
    }

    private List<String> defaultTokens(List<String> configured, List<String> defaults) {
        if (configured != null && !configured.isEmpty()) {
            return configured;
        }
        return defaults;
    }

    private List<String> defaultStripTokens() {
        return List.of("recover", "reprint", "special", "limited", "set", "box", "bundle", "revised");
    }

    private List<String> defaultRecoverTokens() {
        return List.of("recover", "reprint");
    }

    private List<String> defaultSetTokens() {
        return List.of("set", "box", "bundle");
    }

    private List<String> defaultSpecialTokens() {
        return List.of("special", "limited", "anniversary");
    }

    private record GroupEntry(BookHit hit, int order, double score) {}

    private class Group {
        private final List<GroupEntry> entries = new ArrayList<>();

        void add(BookHit hit, int order) {
            double score = score(hit);
            entries.add(new GroupEntry(hit, order, score));
        }

        GroupEntry pickBest(String queryText, MaterialGroupingProperties props) {
            if (entries.isEmpty()) {
                return null;
            }
            boolean queryPrefersSet = containsAny(queryText, defaultTokens(props.getSetTokens(), defaultSetTokens()));
            Comparator<GroupEntry> comparator = Comparator
                .comparingDouble((GroupEntry entry) -> adjustedScore(entry, queryPrefersSet, props))
                .thenComparingInt(entry -> -entry.order());
            return entries.stream().max(comparator).orElse(null);
        }

        List<GroupEntry> others(GroupEntry best) {
            List<GroupEntry> rest = new ArrayList<>();
            for (GroupEntry entry : entries) {
                if (best == null || entry != best) {
                    rest.add(entry);
                }
            }
            return rest;
        }

        private double adjustedScore(GroupEntry entry, boolean queryPrefersSet, MaterialGroupingProperties props) {
            double penalty = 0.0;
            BookHit.Source source = entry.hit().getSource();
            List<String> labels = source == null ? List.of() : source.getEditionLabels();
            String title = source == null ? null : source.getTitleKo();
            if (containsAny(labels, defaultTokens(props.getRecoverTokens(), defaultRecoverTokens()))
                || containsAny(title, defaultTokens(props.getRecoverTokens(), defaultRecoverTokens()))) {
                penalty += props.getRecoverPenalty();
            }
            if (!queryPrefersSet && (containsAny(labels, defaultTokens(props.getSetTokens(), defaultSetTokens()))
                || containsAny(title, defaultTokens(props.getSetTokens(), defaultSetTokens())))) {
                penalty += props.getSetPenalty();
            }
            if (containsAny(labels, defaultTokens(props.getSpecialTokens(), defaultSpecialTokens()))
                || containsAny(title, defaultTokens(props.getSpecialTokens(), defaultSpecialTokens()))) {
                penalty += props.getSpecialPenalty();
            }
            return entry.score() - penalty;
        }

        private double score(BookHit hit) {
            return hit == null ? 0.0 : hit.getScore();
        }
    }

    private boolean containsAny(List<String> values, List<String> tokens) {
        if (values == null || values.isEmpty()) {
            return false;
        }
        Set<String> normalizedTokens = new LinkedHashSet<>();
        for (String token : tokens) {
            if (token != null && !token.isBlank()) {
                normalizedTokens.add(token.toLowerCase(Locale.ROOT));
            }
        }
        if (normalizedTokens.isEmpty()) {
            return false;
        }
        for (String value : values) {
            if (value == null) {
                continue;
            }
            String normalized = value.toLowerCase(Locale.ROOT);
            for (String token : normalizedTokens) {
                if (normalized.contains(token)) {
                    return true;
                }
            }
        }
        return false;
    }

    private boolean containsAny(String value, List<String> tokens) {
        if (value == null || value.isBlank()) {
            return false;
        }
        String normalized = value.toLowerCase(Locale.ROOT);
        for (String token : tokens) {
            if (token != null && !token.isBlank() && normalized.contains(token.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }
}
