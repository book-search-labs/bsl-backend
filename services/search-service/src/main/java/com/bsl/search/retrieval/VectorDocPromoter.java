package com.bsl.search.retrieval;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class VectorDocPromoter {
    private final VectorSearchProperties properties;

    public VectorDocPromoter(VectorSearchProperties properties) {
        this.properties = properties;
    }

    public List<String> promote(List<String> docIds) {
        if (docIds == null || docIds.isEmpty() || !isEnabled()) {
            return docIds == null ? List.of() : docIds;
        }
        LinkedHashSet<String> deduped = new LinkedHashSet<>();
        for (String docId : docIds) {
            if (docId == null || docId.isBlank()) {
                continue;
            }
            String base = toBaseDocId(docId);
            if (base == null || base.isBlank()) {
                continue;
            }
            deduped.add(base);
        }
        return new ArrayList<>(deduped);
    }

    private boolean isEnabled() {
        return properties.getPromotion() != null && properties.getPromotion().isEnabled();
    }

    private String toBaseDocId(String docId) {
        String separators = properties.getPromotion() == null ? null : properties.getPromotion().getSeparators();
        if (separators == null || separators.isBlank()) {
            return docId;
        }
        String[] tokens = separators.split(",");
        String base = docId;
        for (String token : tokens) {
            String sep = token.trim();
            if (sep.isEmpty()) {
                continue;
            }
            int idx = base.indexOf(sep);
            if (idx > 0) {
                base = base.substring(0, idx);
            }
        }
        return base;
    }
}
