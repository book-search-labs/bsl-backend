package com.bsl.bff.authority.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public class AuthorityMergeGroupDto {
    @JsonProperty("group_id")
    private Long groupId;

    private String status;

    @JsonProperty("rule_version")
    private String ruleVersion;

    @JsonProperty("group_key")
    private String groupKey;

    @JsonProperty("master_material_id")
    private String masterMaterialId;

    private Object members;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;

    public Long getGroupId() {
        return groupId;
    }

    public void setGroupId(Long groupId) {
        this.groupId = groupId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getRuleVersion() {
        return ruleVersion;
    }

    public void setRuleVersion(String ruleVersion) {
        this.ruleVersion = ruleVersion;
    }

    public String getGroupKey() {
        return groupKey;
    }

    public void setGroupKey(String groupKey) {
        this.groupKey = groupKey;
    }

    public String getMasterMaterialId() {
        return masterMaterialId;
    }

    public void setMasterMaterialId(String masterMaterialId) {
        this.masterMaterialId = masterMaterialId;
    }

    public Object getMembers() {
        return members;
    }

    public void setMembers(Object members) {
        this.members = members;
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
