package com.bsl.bff.security;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class PermissionResolver {
    private final Map<Pattern, String> rules = new LinkedHashMap<>();

    public PermissionResolver() {
        rules.put(Pattern.compile("^/admin/ops/reindex-jobs.*"), "OPS_REINDEX_RUN");
        rules.put(Pattern.compile("^/admin/ops/job-runs.*"), "OPS_JOB_RUN");
        rules.put(Pattern.compile("^/admin/ops/tasks.*"), "OPS_TASK_MANAGE");
        rules.put(Pattern.compile("^/admin/ops/autocomplete.*"), "OPS_AUTOCOMPLETE_MANAGE");
        rules.put(Pattern.compile("^/admin/rag.*"), "RAG_OPS");
        rules.put(Pattern.compile("^/admin/authority.*"), "AUTHORITY_MANAGE");
        rules.put(Pattern.compile("^/admin/policies.*"), "POLICY_EDIT");
        rules.put(Pattern.compile("^/admin/experiments.*"), "EXPERIMENT_ROLLOUT");
        rules.put(Pattern.compile("^/admin/models.*"), "MODEL_ROLLOUT");
        rules.put(Pattern.compile("^/admin/products.*"), "PRODUCT_EDIT");
        rules.put(Pattern.compile("^/admin/sellers.*"), "PRODUCT_EDIT");
        rules.put(Pattern.compile("^/admin/skus.*"), "PRODUCT_EDIT");
        rules.put(Pattern.compile("^/admin/offers.*"), "PRODUCT_EDIT");
        rules.put(Pattern.compile("^/admin/inventory.*"), "INVENTORY_MANAGE");
        rules.put(Pattern.compile("^/admin/payments.*"), "PAYMENT_REFUND");
        rules.put(Pattern.compile("^/admin/refunds.*"), "PAYMENT_REFUND");
        rules.put(Pattern.compile("^/admin/settlements.*"), "PAYMENT_REFUND");
        rules.put(Pattern.compile("^/admin/shipments.*"), "SHIPPING_MANAGE");
    }

    public String resolve(String path) {
        if (path == null) {
            return null;
        }
        for (Map.Entry<Pattern, String> entry : rules.entrySet()) {
            if (entry.getKey().matcher(path).matches()) {
                return entry.getValue();
            }
        }
        return null;
    }
}
