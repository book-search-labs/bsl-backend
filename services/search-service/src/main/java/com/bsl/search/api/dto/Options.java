package com.bsl.search.api.dto;

public class Options {
    private Integer size;
    private Integer from;
    private Boolean enableVector;
    private Integer rrfK;
    private Boolean debug;
    private Boolean explain;
    private Integer timeoutMs;

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

    public Boolean getDebug() {
        return debug;
    }

    public void setDebug(Boolean debug) {
        this.debug = debug;
    }

    public Boolean getExplain() {
        return explain;
    }

    public void setExplain(Boolean explain) {
        this.explain = explain;
    }

    public Integer getTimeoutMs() {
        return timeoutMs;
    }

    public void setTimeoutMs(Integer timeoutMs) {
        this.timeoutMs = timeoutMs;
    }
}
