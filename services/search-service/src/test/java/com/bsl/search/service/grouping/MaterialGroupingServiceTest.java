package com.bsl.search.service.grouping;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.bsl.search.api.dto.BookHit;
import java.util.List;
import org.junit.jupiter.api.Test;

class MaterialGroupingServiceTest {

    @Test
    void groupingPrefersNonRecoverEdition() {
        MaterialGroupingProperties props = new MaterialGroupingProperties();
        props.setEnabled(true);
        props.setRecoverPenalty(0.2);
        MaterialGroupingService service = new MaterialGroupingService(props);

        BookHit recover = buildHit("b1", 1.0, "Harry Potter", List.of("Joanne Rowling"), List.of("recover"));
        BookHit normal = buildHit("b2", 0.9, "Harry Potter", List.of("Joanne Rowling"), List.of());

        List<BookHit> grouped = service.apply("Harry Potter", List.of(recover, normal), 1);

        assertEquals(1, grouped.size());
        assertEquals("b2", grouped.get(0).getDocId());
    }

    private BookHit buildHit(String docId, double score, String title, List<String> authors, List<String> labels) {
        BookHit hit = new BookHit();
        hit.setDocId(docId);
        hit.setScore(score);
        BookHit.Source source = new BookHit.Source();
        source.setTitleKo(title);
        source.setAuthors(authors);
        source.setEditionLabels(labels);
        hit.setSource(source);
        return hit;
    }
}
