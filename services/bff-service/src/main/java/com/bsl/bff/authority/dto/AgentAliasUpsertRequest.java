package com.bsl.bff.authority.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AgentAliasUpsertRequest {
    @JsonProperty("alias_name")
    private String aliasName;

    @JsonProperty("canonical_name")
    private String canonicalName;

    @JsonProperty("canonical_agent_id")
    private String canonicalAgentId;

    private String status;

    public String getAliasName() {
        return aliasName;
    }

    public void setAliasName(String aliasName) {
        this.aliasName = aliasName;
    }

    public String getCanonicalName() {
        return canonicalName;
    }

    public void setCanonicalName(String canonicalName) {
        this.canonicalName = canonicalName;
    }

    public String getCanonicalAgentId() {
        return canonicalAgentId;
    }

    public void setCanonicalAgentId(String canonicalAgentId) {
        this.canonicalAgentId = canonicalAgentId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
