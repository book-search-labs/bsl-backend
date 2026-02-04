package com.bsl.bff.api;

import com.bsl.bff.api.dto.KdcCategoryResponse;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.kdc.KdcCategoryRepository;
import com.bsl.bff.kdc.KdcCategoryRepository.KdcCategoryRow;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class KdcCategoryController {
    private final KdcCategoryRepository repository;

    public KdcCategoryController(KdcCategoryRepository repository) {
        this.repository = repository;
    }

    @GetMapping({"/categories/kdc", "/v1/categories/kdc"})
    public KdcCategoryResponse listKdcCategories() {
        RequestContext context = RequestContextHolder.get();
        List<KdcCategoryRow> rows = repository.listAll();

        Map<Long, KdcCategoryResponse.KdcCategoryNode> nodes = new LinkedHashMap<>();
        List<KdcCategoryResponse.KdcCategoryNode> roots = new ArrayList<>();

        for (KdcCategoryRow row : rows) {
            if (row == null || row.id() == null) {
                continue;
            }
            KdcCategoryResponse.KdcCategoryNode node = new KdcCategoryResponse.KdcCategoryNode();
            node.setId(row.id());
            node.setCode(row.code());
            node.setName(row.name());
            node.setDepth(row.depth());
            node.setChildren(new ArrayList<>());
            nodes.put(row.id(), node);

            if (row.parentId() == null) {
                roots.add(node);
                continue;
            }

            KdcCategoryResponse.KdcCategoryNode parent = nodes.get(row.parentId());
            if (parent == null) {
                roots.add(node);
            } else {
                parent.getChildren().add(node);
            }
        }

        KdcCategoryResponse response = new KdcCategoryResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setCategories(roots);
        return response;
    }
}
