package com.bsl.commerce.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;

@ExtendWith(MockitoExtension.class)
class HomeCollectionRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @Test
    void bestsellerFallbackUsesOrdersStatusColumn() {
        when(jdbcTemplate.queryForList(anyString(), any(Object[].class))).thenReturn(List.of());

        HomeCollectionRepository repository = new HomeCollectionRepository(jdbcTemplate);
        repository.listFallbackItems("bestseller", 8, Set.of());

        ArgumentCaptor<String> sqlCaptor = ArgumentCaptor.forClass(String.class);
        verify(jdbcTemplate).queryForList(sqlCaptor.capture(), any(Object[].class));
        String sql = sqlCaptor.getValue();
        assertThat(sql).contains("WHERE o.status IN");
        assertThat(sql).contains("DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 7 DAY)");
    }
}
