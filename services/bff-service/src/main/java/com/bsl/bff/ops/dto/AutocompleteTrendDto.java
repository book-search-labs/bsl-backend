package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public class AutocompleteTrendDto {
    @JsonProperty("suggest_id")
    private String suggestId;
    private String text;
    private String type;
    private String lang;
    @JsonProperty("impressions_7d")
    private Double impressions7d;
    @JsonProperty("clicks_7d")
    private Double clicks7d;
    @JsonProperty("ctr_7d")
    private Double ctr7d;
    @JsonProperty("popularity_7d")
    private Double popularity7d;
    @JsonProperty("last_seen_at")
    private Instant lastSeenAt;
    @JsonProperty("updated_at")
    private Instant updatedAt;

    public String getSuggestId() {
        return suggestId;
    }

    public void setSuggestId(String suggestId) {
        this.suggestId = suggestId;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getLang() {
        return lang;
    }

    public void setLang(String lang) {
        this.lang = lang;
    }

    public Double getImpressions7d() {
        return impressions7d;
    }

    public void setImpressions7d(Double impressions7d) {
        this.impressions7d = impressions7d;
    }

    public Double getClicks7d() {
        return clicks7d;
    }

    public void setClicks7d(Double clicks7d) {
        this.clicks7d = clicks7d;
    }

    public Double getCtr7d() {
        return ctr7d;
    }

    public void setCtr7d(Double ctr7d) {
        this.ctr7d = ctr7d;
    }

    public Double getPopularity7d() {
        return popularity7d;
    }

    public void setPopularity7d(Double popularity7d) {
        this.popularity7d = popularity7d;
    }

    public Instant getLastSeenAt() {
        return lastSeenAt;
    }

    public void setLastSeenAt(Instant lastSeenAt) {
        this.lastSeenAt = lastSeenAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
