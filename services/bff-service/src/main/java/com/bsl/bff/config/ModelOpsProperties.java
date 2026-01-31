package com.bsl.bff.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.model-ops")
public class ModelOpsProperties {
    private String registryPath = "services/model-inference-service/app/config/model_registry.json";
    private String evalRunsDir = "evaluation/eval_runs";

    public String getRegistryPath() {
        return registryPath;
    }

    public void setRegistryPath(String registryPath) {
        this.registryPath = registryPath;
    }

    public String getEvalRunsDir() {
        return evalRunsDir;
    }

    public void setEvalRunsDir(String evalRunsDir) {
        this.evalRunsDir = evalRunsDir;
    }
}
