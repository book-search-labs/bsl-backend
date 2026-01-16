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
import com.bsl.search.ranking.RankingGateway;
import com.bsl.search.ranking.RankingUnavailableException;
import com.bsl.search.ranking.dto.RerankRequest;
import com.bsl.search.ranking.dto.RerankResponse;
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
    private final RankingGateway rankingGateway;

    public HybridSearchService(OpenSearchGateway openSearchGateway, ToyEmbedder toyEmbedder, RankingGateway rankingGateway) {
        this.openSearchGateway = openSearchGateway;
        this.toyEmbedder = toyEmbedder;
        this.rankingGateway = rankingGateway;
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
        List<String> fusedDocIds = toDocIds(fused);
        Map<String, JsonNode> sources = fusedDocIds.isEmpty()
            ? Collections.emptyMap()
            : openSearchGateway.mgetSources(fusedDocIds);

        boolean rankingApplied = false;
        List<BookHit> hits;

        if (fused.isEmpty()) {
            hits = Collections.emptyList();
        } else {
            List<RerankRequest.Candidate> rerankCandidates = buildRerankCandidates(fused, sources);
            Map<String, RrfFusion.Candidate> fusedById = toCandidateMap(fused);
            int rerankSize = Math.min(from + size, fused.size());

            try {
                RerankResponse rerankResponse = rankingGateway.rerank(
                    query,
                    rerankCandidates,
                    rerankSize,
                    traceId,
                    requestId
                );

                if (rerankResponse != null && rerankResponse.getHits() != null) {
                    rankingApplied = true;
                    hits = buildHitsFromRanking(rerankResponse.getHits(), fusedById, from, size, sources);
                } else {
                    hits = buildHitsFromFused(fused, from, size, sources);
                }
            } catch (RankingUnavailableException e) {
                hits = buildHitsFromFused(fused, from, size, sources);
            }
        }

        long tookMs = (System.nanoTime() - started) / 1_000_000L;
        SearchResponse response = new SearchResponse();
        response.setTraceId(traceId);
        response.setRequestId(requestId);
        response.setTookMs(tookMs);
        response.setRankingApplied(rankingApplied);
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

    private List<String> toDocIds(List<RrfFusion.Candidate> candidates) {
        List<String> docIds = new ArrayList<>(candidates.size());
        for (RrfFusion.Candidate candidate : candidates) {
            docIds.add(candidate.getDocId());
        }
        return docIds;
    }

    private Map<String, RrfFusion.Candidate> toCandidateMap(List<RrfFusion.Candidate> candidates) {
        Map<String, RrfFusion.Candidate> byId = new HashMap<>();
        for (RrfFusion.Candidate candidate : candidates) {
            byId.put(candidate.getDocId(), candidate);
        }
        return byId;
    }

    private List<RerankRequest.Candidate> buildRerankCandidates(
        List<RrfFusion.Candidate> candidates,
        Map<String, JsonNode> sources
    ) {
        List<RerankRequest.Candidate> rerankCandidates = new ArrayList<>(candidates.size());
        for (RrfFusion.Candidate candidate : candidates) {
            RerankRequest.Candidate rerankCandidate = new RerankRequest.Candidate();
            rerankCandidate.setDocId(candidate.getDocId());

            RerankRequest.Features features = new RerankRequest.Features();
            features.setLexRank(candidate.getLexRank());
            features.setVecRank(candidate.getVecRank());
            features.setRrfScore(candidate.getScore());

            JsonNode source = sources.get(candidate.getDocId());
            if (source != null && !source.isMissingNode()) {
                features.setIssuedYear(readInteger(source, "issued_year"));
                features.setVolume(readInteger(source, "volume"));
                features.setEditionLabels(extractEditionLabels(source));
            } else {
                features.setEditionLabels(Collections.emptyList());
            }

            rerankCandidate.setFeatures(features);
            rerankCandidates.add(rerankCandidate);
        }
        return rerankCandidates;
    }

    private List<BookHit> buildHitsFromRanking(
        List<RerankResponse.Hit> rankHits,
        Map<String, RrfFusion.Candidate> fusedById,
        int from,
        int size,
        Map<String, JsonNode> sources
    ) {
        int total = rankHits.size();
        int startIndex = Math.min(from, total);
        int endIndex = Math.min(startIndex + size, total);

        List<BookHit> hits = new ArrayList<>(Math.max(endIndex - startIndex, 0));
        for (int i = startIndex; i < endIndex; i++) {
            RerankResponse.Hit rerankHit = rankHits.get(i);
            String docId = rerankHit.getDocId();
            if (docId == null || docId.isEmpty()) {
                continue;
            }
            RrfFusion.Candidate candidate = fusedById.get(docId);

            BookHit hit = new BookHit();
            hit.setDocId(docId);
            hit.setScore(rerankHit.getScore());
            hit.setRank(i + 1);

            BookHit.Debug debug = new BookHit.Debug();
            if (candidate != null) {
                debug.setLexRank(candidate.getLexRank());
                debug.setVecRank(candidate.getVecRank());
                debug.setRrfScore(candidate.getScore());
            }
            debug.setRankingScore(rerankHit.getScore());
            hit.setDebug(debug);
            hit.setSource(mapSource(sources.get(docId)));
            hits.add(hit);
        }
        return hits;
    }

    private List<BookHit> buildHitsFromFused(
        List<RrfFusion.Candidate> fused,
        int from,
        int size,
        Map<String, JsonNode> sources
    ) {
        int total = fused.size();
        int startIndex = Math.min(from, total);
        int endIndex = Math.min(startIndex + size, total);

        List<BookHit> hits = new ArrayList<>(Math.max(endIndex - startIndex, 0));
        for (int i = startIndex; i < endIndex; i++) {
            RrfFusion.Candidate candidate = fused.get(i);
            BookHit hit = new BookHit();
            hit.setDocId(candidate.getDocId());
            hit.setScore(candidate.getScore());
            hit.setRank(i + 1);

            BookHit.Debug debug = new BookHit.Debug();
            debug.setLexRank(candidate.getLexRank());
            debug.setVecRank(candidate.getVecRank());
            debug.setRrfScore(candidate.getScore());
            hit.setDebug(debug);

            hit.setSource(mapSource(sources.get(candidate.getDocId())));
            hits.add(hit);
        }
        return hits;
    }

    private BookHit.Source mapSource(JsonNode source) {
        if (source == null || source.isMissingNode()) {
            return null;
        }
        BookHit.Source mapped = new BookHit.Source();
        mapped.setTitleKo(source.path("title_ko").asText(null));
        mapped.setPublisherName(source.path("publisher_name").asText(null));
        mapped.setIssuedYear(readInteger(source, "issued_year"));
        mapped.setVolume(readInteger(source, "volume"));
        mapped.setEditionLabels(extractEditionLabels(source));

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

    private Integer readInteger(JsonNode source, String fieldName) {
        JsonNode node = source.path(fieldName);
        if (node.isMissingNode() || node.isNull()) {
            return null;
        }
        return node.asInt();
    }

    private List<String> extractEditionLabels(JsonNode source) {
        List<String> editionLabels = new ArrayList<>();
        for (JsonNode labelNode : source.path("edition_labels")) {
            if (labelNode.isTextual()) {
                editionLabels.add(labelNode.asText());
            }
        }
        return editionLabels;
    }
}
