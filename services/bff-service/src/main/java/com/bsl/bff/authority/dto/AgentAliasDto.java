package com.bsl.bff.authority.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public class AgentAliasDto {
    @JsonProperty("alias_id")
    private Long aliasId;

    @JsonProperty("alias_name")
    private String aliasName;

    @JsonProperty("canonical_name")
    private String canonicalName;

    @JsonProperty("canonical_agent_id")
    private String canonicalAgentId;

    private String status;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;

    public Long getAliasId() {
        return aliasId;
    }

    public void setAliasId(Long aliasId) {
        this.aliasId = aliasId;
    }

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

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
