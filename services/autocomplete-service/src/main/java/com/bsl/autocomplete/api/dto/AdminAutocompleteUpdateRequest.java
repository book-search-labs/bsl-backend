package com.bsl.autocomplete.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AdminAutocompleteUpdateRequest {
    private Integer weight;

    @JsonProperty("is_blocked")
    private Boolean blocked;

    public Integer getWeight() {
        return weight;
    }

    public void setWeight(Integer weight) {
        this.weight = weight;
    }

    public Boolean getBlocked() {
        return blocked;
    }

    public void setBlocked(Boolean blocked) {
        this.blocked = blocked;
    }
}
