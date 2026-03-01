package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.HomePanelRepository;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class HomePanelService {
    private static final int DEFAULT_LIMIT = 31;
    private static final int MAX_LIMIT = 100;
    private static final Set<String> ALLOWED_TYPES = Set.of("EVENT", "NOTICE");

    private final HomePanelRepository homePanelRepository;

    public HomePanelService(HomePanelRepository homePanelRepository) {
        this.homePanelRepository = homePanelRepository;
    }

    public QueryOptions resolveQuery(Integer limit, String type) {
        int resolvedLimit = limit == null ? DEFAULT_LIMIT : Math.min(Math.max(limit, 1), MAX_LIMIT);
        String resolvedType = normalizeType(type);
        return new QueryOptions(resolvedLimit, resolvedType);
    }

    public List<Map<String, Object>> listActivePanels(QueryOptions options) {
        return homePanelRepository.listActiveItems(options.panelType(), options.limit());
    }

    public Map<String, Object> getActivePanel(long itemId) {
        Map<String, Object> item = homePanelRepository.findActiveItemById(itemId);
        if (item == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "home panel item not found");
        }
        return item;
    }

    public long countActivePanels(QueryOptions options) {
        return homePanelRepository.countActiveItems(options.panelType());
    }

    private String normalizeType(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (!ALLOWED_TYPES.contains(normalized)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "type must be EVENT or NOTICE");
        }
        return normalized;
    }

    public record QueryOptions(int limit, String panelType) {
    }
}
