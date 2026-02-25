package com.bsl.commerce.service;

import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.HomeCollectionRepository;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class HomeCollectionService {
    private static final int DEFAULT_LIMIT_PER_SECTION = 8;
    private static final int MAX_LIMIT_PER_SECTION = 24;

    private static final List<SectionMeta> SECTION_ORDER = List.of(
        new SectionMeta("bestseller", "BESTSELLER", "이번 주 베스트셀러", "지금 가장 많이 찾는 도서를 모았습니다.", "/search?q=베스트셀러"),
        new SectionMeta("new", "NEW_RELEASE", "신간 · 예약구매", "곧 출간하는 도서를 예약구매로 먼저 만나보세요.", "/preorders"),
        new SectionMeta("editor", "EDITOR_PICK", "에디터 추천", "감성적인 에세이와 문학 작품을 큐레이션했습니다.", "/search?q=에세이")
    );

    private final HomeCollectionRepository homeCollectionRepository;

    public HomeCollectionService(HomeCollectionRepository homeCollectionRepository) {
        this.homeCollectionRepository = homeCollectionRepository;
    }

    public QueryOptions resolveQuery(Integer limitPerSection) {
        int resolved = limitPerSection == null
            ? DEFAULT_LIMIT_PER_SECTION
            : Math.min(Math.max(limitPerSection, 1), MAX_LIMIT_PER_SECTION);
        return new QueryOptions(resolved);
    }

    public List<Map<String, Object>> listSections(QueryOptions options) {
        Set<String> usedMaterialIds = new HashSet<>();
        List<Map<String, Object>> sections = new ArrayList<>();

        for (SectionMeta meta : SECTION_ORDER) {
            List<Map<String, Object>> configured = homeCollectionRepository.listConfiguredItems(
                meta.sectionKey(),
                options.limitPerSection(),
                usedMaterialIds
            );

            List<Map<String, Object>> rows = new ArrayList<>(configured);
            int remain = options.limitPerSection() - rows.size();
            if (remain > 0) {
                rows.addAll(homeCollectionRepository.listFallbackItems(meta.key(), remain, usedMaterialIds));
            }

            List<Map<String, Object>> items = new ArrayList<>();
            for (Map<String, Object> row : rows) {
                Map<String, Object> item = toItem(row);
                String docId = JdbcUtils.asString(item.get("doc_id"));
                if (docId != null && !docId.isBlank()) {
                    usedMaterialIds.add(docId);
                }
                items.add(item);
            }

            Map<String, Object> section = new LinkedHashMap<>();
            section.put("key", meta.key());
            section.put("title", meta.title());
            section.put("note", meta.note());
            section.put("link", meta.link());
            section.put("items", items);
            sections.add(section);
        }

        return sections;
    }

    private Map<String, Object> toItem(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("doc_id", JdbcUtils.asString(row.get("doc_id")));
        item.put("title_ko", JdbcUtils.asString(row.get("title_ko")));
        String author = JdbcUtils.asString(row.get("author_name"));
        if (author == null || author.isBlank()) {
            item.put("authors", List.of());
        } else {
            item.put("authors", List.of(author));
        }
        item.put("publisher_name", JdbcUtils.asString(row.get("publisher_name")));
        item.put("issued_year", JdbcUtils.asInt(row.get("issued_year")));
        item.put("edition_labels", List.of());
        return item;
    }

    public record QueryOptions(int limitPerSection) {
    }

    private record SectionMeta(String key, String sectionKey, String title, String note, String link) {
    }
}
