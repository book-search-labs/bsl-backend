package com.bsl.bff.authority.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AuthorityMergeGroupResolveRequest {
    @JsonProperty("master_material_id")
    private String masterMaterialId;

    private String status;

    public String getMasterMaterialId() {
        return masterMaterialId;
    }

    public void setMasterMaterialId(String masterMaterialId) {
        this.masterMaterialId = masterMaterialId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
