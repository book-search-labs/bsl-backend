package com.bsl.autocomplete.api.dto;

public class AdminAutocompleteUpdateResponse {
    private AdminAutocompleteResponse.Suggestion suggestion;

    public AdminAutocompleteResponse.Suggestion getSuggestion() {
        return suggestion;
    }

    public void setSuggestion(AdminAutocompleteResponse.Suggestion suggestion) {
        this.suggestion = suggestion;
    }
}
