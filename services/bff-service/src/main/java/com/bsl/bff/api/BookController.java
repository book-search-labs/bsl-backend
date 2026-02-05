package com.bsl.bff.api;

import com.bsl.bff.api.dto.BffBookDetailResponse;
import com.bsl.bff.client.SearchServiceClient;
import com.bsl.bff.client.dto.BookDetailServiceResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.outbox.OutboxService;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController {
    private final SearchServiceClient searchServiceClient;
    private final OutboxService outboxService;

    public BookController(SearchServiceClient searchServiceClient, OutboxService outboxService) {
        this.searchServiceClient = searchServiceClient;
        this.outboxService = outboxService;
    }

    @GetMapping({"/books/{docId}", "/v1/books/{docId}"})
    public BffBookDetailResponse getBook(@PathVariable("docId") String docId) {
        RequestContext context = RequestContextHolder.get();
        if (docId == null || docId.trim().isEmpty()) {
            throw new BadRequestException("docId is required");
        }

        BookDetailServiceResponse downstream = searchServiceClient.fetchBook(docId, context);
        if (downstream == null) {
            throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "Book not found");
        }

        BffBookDetailResponse response = new BffBookDetailResponse();
        response.setVersion("v1");
        response.setDocId(downstream.getDocId());
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setTookMs(downstream.getTookMs());

        if (downstream.getSource() == null) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "search_service_error", "Book detail missing source");
        }

        BffBookDetailResponse.Source source = new BffBookDetailResponse.Source();
        source.setTitleKo(downstream.getSource().getTitleKo());
        source.setAuthors(downstream.getSource().getAuthors());
        source.setPublisherName(downstream.getSource().getPublisherName());
        source.setIssuedYear(downstream.getSource().getIssuedYear());
        source.setVolume(downstream.getSource().getVolume());
        source.setEditionLabels(downstream.getSource().getEditionLabels());
        response.setSource(source);

        recordOutbox("book_view", "book", context, Map.of(
            "doc_id", docId
        ));

        return response;
    }

    private void recordOutbox(String eventType, String aggregateType, RequestContext context, Map<String, Object> payload) {
        if (context == null) {
            return;
        }
        Map<String, Object> enriched = new HashMap<>(payload);
        enriched.put("request_id", context.getRequestId());
        enriched.put("trace_id", context.getTraceId());
        outboxService.record(eventType, aggregateType, context.getRequestId(), enriched);
    }
}
