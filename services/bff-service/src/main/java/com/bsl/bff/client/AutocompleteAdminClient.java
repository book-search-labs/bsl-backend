package com.bsl.bff.client;

import com.bsl.bff.client.dto.AutocompleteAdminServiceResponse;
import com.bsl.bff.client.dto.AutocompleteAdminServiceUpdateResponse;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
import com.bsl.bff.ops.dto.AutocompleteSuggestionUpdateRequest;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class AutocompleteAdminClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public AutocompleteAdminClient(RestTemplate autocompleteServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = autocompleteServiceRestTemplate;
        this.properties = downstreamProperties.getAutocompleteService();
    }

    public AutocompleteAdminServiceResponse searchSuggestions(
        String query,
        Integer size,
        Boolean includeBlocked,
        RequestContext context
    ) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromHttpUrl(properties.getBaseUrl())
            .path("/internal/autocomplete/suggestions")
            .queryParam("q", query);
        if (size != null) {
            builder.queryParam("size", size);
        }
        if (includeBlocked != null) {
            builder.queryParam("include_blocked", includeBlocked);
        }
        String url = builder.build().toUriString();

        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        try {
            ResponseEntity<AutocompleteAdminServiceResponse> response = restTemplate.exchange(
                url,
                HttpMethod.GET,
                entity,
                AutocompleteAdminServiceResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "autocomplete_admin_timeout", "Autocomplete admin timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "autocomplete_admin_bad_request" : "autocomplete_admin_error";
            throw new DownstreamException(status, code, "Autocomplete admin error");
        }
    }

    public AutocompleteAdminServiceUpdateResponse updateSuggestion(
        String suggestId,
        AutocompleteSuggestionUpdateRequest request,
        RequestContext context
    ) {
        String url = UriComponentsBuilder.fromHttpUrl(properties.getBaseUrl())
            .path("/internal/autocomplete/suggestions/{id}")
            .buildAndExpand(suggestId)
            .toUriString();

        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<AutocompleteSuggestionUpdateRequest> entity = new HttpEntity<>(request, headers);

        try {
            ResponseEntity<AutocompleteAdminServiceUpdateResponse> response = restTemplate.exchange(
                url,
                HttpMethod.POST,
                entity,
                AutocompleteAdminServiceUpdateResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "autocomplete_admin_timeout", "Autocomplete admin timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "autocomplete_admin_bad_request" : "autocomplete_admin_error";
            throw new DownstreamException(status, code, "Autocomplete admin error");
        }
    }
}
