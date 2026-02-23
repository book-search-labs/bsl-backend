package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anySet;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.repository.HomeCollectionRepository;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class HomeCollectionServiceTest {

    @Mock
    private HomeCollectionRepository homeCollectionRepository;

    @Test
    void resolveQueryDefaultsAndClamps() {
        HomeCollectionService service = new HomeCollectionService(homeCollectionRepository);

        HomeCollectionService.QueryOptions defaults = service.resolveQuery(null);
        HomeCollectionService.QueryOptions clamped = service.resolveQuery(999);

        assertThat(defaults.limitPerSection()).isEqualTo(8);
        assertThat(clamped.limitPerSection()).isEqualTo(24);
    }

    @Test
    void listSectionsReturnsThreeSectionsWithItems() {
        HomeCollectionService service = new HomeCollectionService(homeCollectionRepository);
        HomeCollectionService.QueryOptions options = service.resolveQuery(2);

        when(homeCollectionRepository.listConfiguredItems(eq("BESTSELLER"), eq(2), anySet()))
            .thenReturn(List.of(Map.of(
                "doc_id", "nlk:A",
                "title_ko", "베스트 도서",
                "author_name", "홍길동",
                "publisher_name", "BSL",
                "issued_year", 2025
            )));
        when(homeCollectionRepository.listConfiguredItems(eq("NEW_RELEASE"), eq(2), anySet()))
            .thenReturn(List.of());
        when(homeCollectionRepository.listConfiguredItems(eq("EDITOR_PICK"), eq(2), anySet()))
            .thenReturn(List.of());

        when(homeCollectionRepository.listFallbackItems(eq("bestseller"), eq(1), anySet()))
            .thenReturn(List.of(Map.of(
                "doc_id", "nlk:B",
                "title_ko", "대체 베스트",
                "publisher_name", "BSL",
                "issued_year", 2024
            )));
        when(homeCollectionRepository.listFallbackItems(eq("new"), eq(2), anySet()))
            .thenReturn(List.of(Map.of(
                "doc_id", "nlk:C",
                "title_ko", "신간 도서",
                "publisher_name", "BSL",
                "issued_year", 2026
            )));
        when(homeCollectionRepository.listFallbackItems(eq("editor"), eq(2), anySet()))
            .thenReturn(List.of(Map.of(
                "doc_id", "nlk:D",
                "title_ko", "에디터 추천 도서",
                "publisher_name", "BSL",
                "issued_year", 2023
            )));

        List<Map<String, Object>> sections = service.listSections(options);

        assertThat(sections).hasSize(3);
        assertThat(sections.get(0).get("key")).isEqualTo("bestseller");
        assertThat((List<?>) sections.get(0).get("items")).hasSize(2);
        assertThat(sections.get(1).get("key")).isEqualTo("new");
        assertThat((List<?>) sections.get(1).get("items")).hasSize(1);
        assertThat(sections.get(2).get("key")).isEqualTo("editor");
        assertThat((List<?>) sections.get(2).get("items")).hasSize(1);

        verify(homeCollectionRepository).listConfiguredItems(eq("BESTSELLER"), eq(2), anySet());
        verify(homeCollectionRepository).listConfiguredItems(eq("NEW_RELEASE"), eq(2), anySet());
        verify(homeCollectionRepository).listConfiguredItems(eq("EDITOR_PICK"), eq(2), anySet());
    }
}
