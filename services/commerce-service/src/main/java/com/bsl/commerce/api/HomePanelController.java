package com.bsl.commerce.api;

import com.bsl.commerce.common.RequestContext;
import com.bsl.commerce.common.RequestContextHolder;
import com.bsl.commerce.service.HomeCollectionService;
import com.bsl.commerce.service.HomePanelService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class HomePanelController {
    private final HomePanelService homePanelService;
    private final HomeCollectionService homeCollectionService;

    public HomePanelController(HomePanelService homePanelService, HomeCollectionService homeCollectionService) {
        this.homePanelService = homePanelService;
        this.homeCollectionService = homeCollectionService;
    }

    @GetMapping("/home/panels")
    public Map<String, Object> listPanels(
        @RequestParam(name = "limit", required = false) Integer limit,
        @RequestParam(name = "type", required = false) String type
    ) {
        HomePanelService.QueryOptions options = homePanelService.resolveQuery(limit, type);
        List<Map<String, Object>> items = homePanelService.listActivePanels(options);
        long totalCount = homePanelService.countActivePanels(options);

        Map<String, Object> response = base();
        response.put("items", items);
        response.put("count", items.size());
        response.put("total_count", totalCount);
        response.put("limit", options.limit());
        response.put("type", options.panelType());
        return response;
    }

    @GetMapping("/home/panels/{itemId}")
    public Map<String, Object> getPanel(@PathVariable("itemId") long itemId) {
        Map<String, Object> item = homePanelService.getActivePanel(itemId);
        Map<String, Object> response = base();
        response.put("item", item);
        return response;
    }

    @GetMapping("/home/collections")
    public Map<String, Object> listCollections(
        @RequestParam(name = "limit_per_section", required = false) Integer limitPerSection
    ) {
        HomeCollectionService.QueryOptions options = homeCollectionService.resolveQuery(limitPerSection);
        List<Map<String, Object>> sections = homeCollectionService.listSections(options);

        Map<String, Object> response = base();
        response.put("sections", sections);
        response.put("limit_per_section", options.limitPerSection());
        response.put("count", sections.size());
        return response;
    }

    private Map<String, Object> base() {
        RequestContext context = RequestContextHolder.get();
        Map<String, Object> response = new HashMap<>();
        response.put("version", "v1");
        response.put("trace_id", context == null ? null : context.getTraceId());
        response.put("request_id", context == null ? null : context.getRequestId());
        return response;
    }
}
