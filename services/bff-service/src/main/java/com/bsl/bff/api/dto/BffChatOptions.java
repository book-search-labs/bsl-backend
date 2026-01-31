package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffChatOptions {
    private Boolean stream;
    @JsonProperty("top_k")
    private Integer topK;

    public Boolean getStream() {
        return stream;
    }

    public void setStream(Boolean stream) {
        this.stream = stream;
    }

    public Integer getTopK() {
        return topK;
    }

    public void setTopK(Integer topK) {
        this.topK = topK;
    }
}
