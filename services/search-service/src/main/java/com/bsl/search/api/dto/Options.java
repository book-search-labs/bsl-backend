package com.bsl.search.api.dto;

public class Options {
    private Integer size;
    private Integer from;
    private Boolean enableVector;
    private Integer rrfK;

    public Integer getSize() {
        return size;
    }

    public void setSize(Integer size) {
        this.size = size;
    }

    public Integer getFrom() {
        return from;
    }

    public void setFrom(Integer from) {
        this.from = from;
    }

    public Boolean getEnableVector() {
        return enableVector;
    }

    public void setEnableVector(Boolean enableVector) {
        this.enableVector = enableVector;
    }

    public Integer getRrfK() {
        return rrfK;
    }

    public void setRrfK(Integer rrfK) {
        this.rrfK = rrfK;
    }
}
