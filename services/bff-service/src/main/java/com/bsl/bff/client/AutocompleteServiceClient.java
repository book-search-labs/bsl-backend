package com.bsl.bff.client;

import com.bsl.bff.client.dto.AutocompleteServiceResponse;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.DownstreamHeaders;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.DownstreamProperties;
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
public class AutocompleteServiceClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public AutocompleteServiceClient(RestTemplate autocompleteServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = autocompleteServiceRestTemplate;
        this.properties = downstreamProperties.getAutocompleteService();
    }

    public AutocompleteServiceResponse autocomplete(String query, Integer size, RequestContext context) {
        String url = UriComponentsBuilder.fromHttpUrl(properties.getBaseUrl())
            .path("/autocomplete")
            .queryParam("q", query)
            .queryParam("size", size)
            .build()
            .toUriString();

        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        try {
            ResponseEntity<AutocompleteServiceResponse> response = restTemplate.exchange(
                url,
                HttpMethod.GET,
                entity,
                AutocompleteServiceResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "autocomplete_service_timeout", "Autocomplete service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "autocomplete_service_bad_request" : "autocomplete_service_error";
            throw new DownstreamException(status, code, "Autocomplete service error");
        }
    }
}
