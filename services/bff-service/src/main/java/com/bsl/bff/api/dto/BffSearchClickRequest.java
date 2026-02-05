package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffSearchClickRequest {
    @JsonProperty("imp_id")
    private String impId;

    @JsonProperty("doc_id")
    private String docId;

    private Integer position;

    @JsonProperty("query_hash")
    private String queryHash;

    @JsonProperty("experiment_id")
    private String experimentId;

    @JsonProperty("policy_id")
    private String policyId;

    public String getImpId() {
        return impId;
    }

    public void setImpId(String impId) {
        this.impId = impId;
    }

    public String getDocId() {
        return docId;
    }

    public void setDocId(String docId) {
        this.docId = docId;
    }

    public Integer getPosition() {
        return position;
    }

    public void setPosition(Integer position) {
        this.position = position;
    }

    public String getQueryHash() {
        return queryHash;
    }

    public void setQueryHash(String queryHash) {
        this.queryHash = queryHash;
    }

    public String getExperimentId() {
        return experimentId;
    }

    public void setExperimentId(String experimentId) {
        this.experimentId = experimentId;
    }

    public String getPolicyId() {
        return policyId;
    }

    public void setPolicyId(String policyId) {
        this.policyId = policyId;
    }
}
