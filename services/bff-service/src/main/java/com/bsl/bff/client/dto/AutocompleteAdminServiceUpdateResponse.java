package com.bsl.bff.client.dto;

import com.bsl.bff.ops.dto.AutocompleteSuggestionDto;

public class AutocompleteAdminServiceUpdateResponse {
    private AutocompleteSuggestionDto suggestion;

    public AutocompleteSuggestionDto getSuggestion() {
        return suggestion;
    }

    public void setSuggestion(AutocompleteSuggestionDto suggestion) {
        this.suggestion = suggestion;
    }
}
