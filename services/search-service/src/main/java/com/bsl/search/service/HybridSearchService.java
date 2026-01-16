package com.bsl.search.service;

import com.bsl.search.api.dto.BookHit;
import com.bsl.search.api.dto.Options;
import com.bsl.search.api.dto.SearchRequest;
import com.bsl.search.api.dto.SearchResponse;
import com.bsl.search.embed.ToyEmbedder;
import com.bsl.search.merge.RrfFusion;
import com.bsl.search.opensearch.OpenSearchGateway;
import com.bsl.search.opensearch.OpenSearchRequestException;
import com.bsl.search.opensearch.OpenSearchUnavailableException;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class HybridSearchService {
    private static final int DEFAULT_SIZE = 10;
    private static final int DEFAULT_FROM = 0;
    private static final int DEFAULT_RRF_K = 60;
    private static final int DEFAULT_LEX_TOP_K = 200;
    private static final int DEFAULT_VEC_TOP_K = 200;

    private final OpenSearchGateway openSearchGateway;
    private final ToyEmbedder toyEmbedder;

    public HybridSearchService(OpenSearchGateway openSearchGateway, ToyEmbedder toyEmbedder) {
        this.openSearchGateway = openSearchGateway;
        this.toyEmbedder = toyEmbedder;
    }

    public SearchResponse search(SearchRequest request, String traceId, String requestId) {
        long started = System.nanoTime();

        Options options = request.getOptions() == null ? new Options() : request.getOptions();
        int size = options.getSize() != null ? Math.max(options.getSize(), 0) : DEFAULT_SIZE;
        int from = options.getFrom() != null ? Math.max(options.getFrom(), 0) : DEFAULT_FROM;
        boolean enableVector = options.getEnableVector() == null || options.getEnableVector();
        int rrfK = options.getRrfK() != null ? options.getRrfK() : DEFAULT_RRF_K;

        String query = request.getQuery().getRaw().trim();

        List<String> lexicalDocIds = openSearchGateway.searchLexical(query, DEFAULT_LEX_TOP_K);
        Map<String, Integer> lexRanks = rankMap(lexicalDocIds);

        Map<String, Integer> vecRanks = Collections.emptyMap();
        if (enableVector) {
            try {
                List<Double> vector = toyEmbedder.embed(query);
                List<String> vecDocIds = openSearchGateway.searchVector(vector, DEFAULT_VEC_TOP_K);
                vecRanks = rankMap(vecDocIds);
            } catch (OpenSearchUnavailableException | OpenSearchRequestException e) {
                vecRanks = Collections.emptyMap();
            }
        }

        List<RrfFusion.Candidate> fused = RrfFusion.fuse(lexRanks, vecRanks, rrfK);
        int total = fused.size();
        int startIndex = Math.min(from, total);
        int endIndex = Math.min(startIndex + size, total);
        List<RrfFusion.Candidate> page = fused.subList(startIndex, endIndex);

        List<String> pageDocIds = new ArrayList<>(page.size());
        for (RrfFusion.Candidate candidate : page) {
            pageDocIds.add(candidate.getDocId());
        }

        Map<String, JsonNode> sources = pageDocIds.isEmpty()
            ? Collections.emptyMap()
            : openSearchGateway.mgetSources(pageDocIds);

        List<BookHit> hits = new ArrayList<>(page.size());
        for (int i = 0; i < page.size(); i++) {
            RrfFusion.Candidate candidate = page.get(i);
            BookHit hit = new BookHit();
            hit.setDocId(candidate.getDocId());
            hit.setScore(candidate.getScore());
            hit.setRank(startIndex + i + 1);

            BookHit.Debug debug = new BookHit.Debug();
            debug.setLexRank(candidate.getLexRank());
            debug.setVecRank(candidate.getVecRank());
            hit.setDebug(debug);

            hit.setSource(mapSource(sources.get(candidate.getDocId())));
            hits.add(hit);
        }

        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        SearchResponse response = new SearchResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setStrategy("hybrid_rrf_v1");
        response.setHits(hits);
        return response;
    }

    private Map<String, Integer> rankMap(List<String> docIds) {
        Map<String, Integer> ranks = new HashMap<>();
        for (int i = 0; i < docIds.size(); i++) {
            String docId = docIds.get(i);
            if (!ranks.containsKey(docId)) {
                ranks.put(docId, i + 1);
            }
        }
        return ranks;
    }

    private BookHit.Source mapSource(JsonNode source) {
        if (source == null || source.isMissingNode()) {
            return null;
        }
        BookHit.Source mapped = new BookHit.Source();
        mapped.setTitleKo(source.path("title_ko").asText(null));
        mapped.setPublisherName(source.path("publisher_name").asText(null));
        mapped.setIssuedYear(source.path("issued_year").isMissingNode() ? null : source.path("issued_year").asInt());
        mapped.setVolume(source.path("volume").isMissingNode() ? null : source.path("volume").asInt());

        List<String> editionLabels = new ArrayList<>();
        for (JsonNode labelNode : source.path("edition_labels")) {
            if (labelNode.isTextual()) {
                editionLabels.add(labelNode.asText());
            }
        }
        mapped.setEditionLabels(editionLabels);

        List<String> authors = new ArrayList<>();
        JsonNode authorsNode = source.path("authors");
        if (authorsNode.isArray()) {
            for (JsonNode authorNode : authorsNode) {
                if (authorNode.isTextual()) {
                    authors.add(authorNode.asText());
                } else if (authorNode.isObject()) {
                    String nameKo = authorNode.path("name_ko").asText(null);
                    String nameEn = authorNode.path("name_en").asText(null);
                    if (nameKo != null && !nameKo.isEmpty()) {
                        authors.add(nameKo);
                    } else if (nameEn != null && !nameEn.isEmpty()) {
                        authors.add(nameEn);
                    }
                }
            }
        }
        mapped.setAuthors(authors);
        return mapped;
    }
}
