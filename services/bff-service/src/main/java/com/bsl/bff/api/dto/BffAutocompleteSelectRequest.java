package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffAutocompleteSelectRequest {
    private String q;
    private String text;
    @JsonProperty("suggest_id")
    private String suggestId;
    private String type;
    private Integer position;
    private String source;
    @JsonProperty("target_id")
    private String targetId;
    @JsonProperty("target_doc_id")
    private String targetDocId;

    public String getQ() {
        return q;
    }

    public void setQ(String q) {
        this.q = q;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public String getSuggestId() {
        return suggestId;
    }

    public void setSuggestId(String suggestId) {
        this.suggestId = suggestId;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Integer getPosition() {
        return position;
    }

    public void setPosition(Integer position) {
        this.position = position;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getTargetId() {
        return targetId;
    }

    public void setTargetId(String targetId) {
        this.targetId = targetId;
    }

    public String getTargetDocId() {
        return targetDocId;
    }

    public void setTargetDocId(String targetDocId) {
        this.targetDocId = targetDocId;
    }
}
