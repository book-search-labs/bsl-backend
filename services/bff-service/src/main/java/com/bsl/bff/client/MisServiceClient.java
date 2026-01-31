package com.bsl.bff.client;

import com.bsl.bff.client.dto.MisModelsResponse;
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
public class MisServiceClient {
    private final RestTemplate restTemplate;
    private final DownstreamProperties.ServiceProperties properties;

    public MisServiceClient(RestTemplate misServiceRestTemplate, DownstreamProperties downstreamProperties) {
        this.restTemplate = misServiceRestTemplate;
        this.properties = downstreamProperties.getMisService();
    }

    public MisModelsResponse listModels(RequestContext context) {
        String url = properties.getBaseUrl() + "/v1/models";
        HttpHeaders headers = DownstreamHeaders.from(context);
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        try {
            ResponseEntity<MisModelsResponse> response = restTemplate.exchange(
                url,
                HttpMethod.GET,
                entity,
                MisModelsResponse.class
            );
            return response.getBody();
        } catch (ResourceAccessException ex) {
            throw new DownstreamException(HttpStatus.SERVICE_UNAVAILABLE, "mis_timeout", "MIS timeout");
        } catch (HttpStatusCodeException ex) {
            HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
            if (status == null) {
                status = HttpStatus.SERVICE_UNAVAILABLE;
            }
            String code = status.is4xxClientError() ? "mis_bad_request" : "mis_error";
            throw new DownstreamException(status, code, "MIS error");
        }
    }
}
