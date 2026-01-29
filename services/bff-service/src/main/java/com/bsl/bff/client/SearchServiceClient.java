package com.bsl.bff.client;

import com.bsl.bff.client.dto.BookDetailServiceResponse;
import com.bsl.bff.client.dto.DownstreamSearchRequest;
import com.bsl.bff.client.dto.SearchServiceResponse;
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

@Component
public class SearchServiceClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public SearchServiceClient(RestTemplate searchServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = searchServiceRestTemplate;
        this.properties = downstreamProperties.getSearchService();
    }

    public SearchServiceResponse search(DownstreamSearchRequest request, RequestContext context) {
        String url = properties.getBaseUrl() + "/search";
        HttpHeaders headers = DownstreamHeaders.from(context);
        headers.add(HttpHeaders.CONTENT_TYPE, "application/json");
        HttpEntity<DownstreamSearchRequest> entity = new HttpEntity<>(request, headers);

        try {
            ResponseEntity<SearchServiceResponse> response = restTemplate.exchange(
                url,
                HttpMethod.POST,
                entity,
                SearchServiceResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "search_service_timeout", "Search service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "search_service_bad_request" : "search_service_error";
            throw new DownstreamException(status, code, "Search service error");
        }
    }

    public BookDetailServiceResponse fetchBook(String docId, RequestContext context) {
        String url = properties.getBaseUrl() + "/books/" + docId;
        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        try {
            ResponseEntity<BookDetailServiceResponse> response = restTemplate.exchange(
                url,
                HttpMethod.GET,
                entity,
                BookDetailServiceResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "search_service_timeout", "Search service timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            if (status == HttpStatus.NOT_FOUND) {
                throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "Book not found");
            }
            String code = status.is4xxClientError() ? "search_service_bad_request" : "search_service_error";
            throw new DownstreamException(status, code, "Search service error");
        }
    }
}
