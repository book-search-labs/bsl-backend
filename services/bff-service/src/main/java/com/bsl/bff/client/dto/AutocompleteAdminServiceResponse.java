package com.bsl.bff.client.dto;

import com.bsl.bff.ops.dto.AutocompleteSuggestionDto;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class AutocompleteAdminServiceResponse {
    @JsonProperty("took_ms")
    private long tookMs;
    private List<AutocompleteSuggestionDto> suggestions;

    public long getTookMs() {
        return tookMs;
    }

    public void setTookMs(long tookMs) {
        this.tookMs = tookMs;
    }

    public List<AutocompleteSuggestionDto> getSuggestions() {
        return suggestions;
    }

    public void setSuggestions(List<AutocompleteSuggestionDto> suggestions) {
        this.suggestions = suggestions;
    }
}
