package com.bsl.bff.security;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class PermissionResolver {
    private final Map<Pattern, String> rules = new LinkedHashMap<>();

    public PermissionResolver() {
        rules.put(Pattern.compile("^/admin/ops/reindex.*"), "OPS_REINDEX_RUN");
        rules.put(Pattern.compile("^/admin/ops/reindex/cancel.*"), "OPS_REINDEX_CANCEL");
        rules.put(Pattern.compile("^/admin/policies.*"), "POLICY_EDIT");
        rules.put(Pattern.compile("^/admin/experiments.*"), "EXPERIMENT_ROLLOUT");
        rules.put(Pattern.compile("^/admin/models.*"), "MODEL_ROLLOUT");
        rules.put(Pattern.compile("^/admin/products.*"), "PRODUCT_EDIT");
        rules.put(Pattern.compile("^/admin/payments/refund.*"), "PAYMENT_REFUND");
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
