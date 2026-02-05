package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffChatFeedbackRequest {
    private String version;
    @JsonProperty("trace_id")
    private String traceId;
    @JsonProperty("request_id")
    private String requestId;
    @JsonProperty("session_id")
    private String sessionId;
    @JsonProperty("message_id")
    private String messageId;
    private String rating;
    @JsonProperty("reason_code")
    private String reasonCode;
    private String comment;
    @JsonProperty("flag_hallucination")
    private Boolean flagHallucination;
    @JsonProperty("flag_insufficient")
    private Boolean flagInsufficient;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getTraceId() {
        return traceId;
    }

    public void setTraceId(String traceId) {
        this.traceId = traceId;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getMessageId() {
        return messageId;
    }

    public void setMessageId(String messageId) {
        this.messageId = messageId;
    }

    public String getRating() {
        return rating;
    }

    public void setRating(String rating) {
        this.rating = rating;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public void setReasonCode(String reasonCode) {
        this.reasonCode = reasonCode;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }

    public Boolean getFlagHallucination() {
        return flagHallucination;
    }

    public void setFlagHallucination(Boolean flagHallucination) {
        this.flagHallucination = flagHallucination;
    }

    public Boolean getFlagInsufficient() {
        return flagInsufficient;
    }

    public void setFlagInsufficient(Boolean flagInsufficient) {
        this.flagInsufficient = flagInsufficient;
    }
}
