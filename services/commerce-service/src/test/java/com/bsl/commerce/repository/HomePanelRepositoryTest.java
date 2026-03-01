package com.bsl.commerce.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;

@ExtendWith(MockitoExtension.class)
class HomePanelRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @Test
    void listActiveItemsUsesNullAliasWhenOptionalColumnsAreMissing() {
        when(jdbcTemplate.queryForObject(anyString(), eq(Integer.class), eq("home_panel_item"), eq("detail_body")))
            .thenReturn(0);
        when(jdbcTemplate.queryForObject(anyString(), eq(Integer.class), eq("home_panel_item"), eq("banner_image_url")))
            .thenReturn(0);
        when(jdbcTemplate.queryForList(anyString(), any(Object[].class))).thenReturn(List.of());

        HomePanelRepository repository = new HomePanelRepository(jdbcTemplate);
        repository.listActiveItems(null, 31);

        ArgumentCaptor<String> sqlCaptor = ArgumentCaptor.forClass(String.class);
        verify(jdbcTemplate).queryForList(sqlCaptor.capture(), any(Object[].class));
        String sql = sqlCaptor.getValue();
        assertThat(sql).contains("NULL AS detail_body");
        assertThat(sql).contains("NULL AS banner_image_url");
    }

    @Test
    void listActiveItemsFallsBackToNullAliasesWhenColumnLookupFails() {
        when(jdbcTemplate.queryForObject(anyString(), eq(Integer.class), eq("home_panel_item"), any()))
            .thenThrow(new RuntimeException("information_schema unavailable"));
        when(jdbcTemplate.queryForList(anyString(), any(Object[].class))).thenReturn(List.of());

        HomePanelRepository repository = new HomePanelRepository(jdbcTemplate);
        repository.listActiveItems("EVENT", 10);

        ArgumentCaptor<String> sqlCaptor = ArgumentCaptor.forClass(String.class);
        verify(jdbcTemplate).queryForList(sqlCaptor.capture(), any(Object[].class));
        String sql = sqlCaptor.getValue();
        assertThat(sql).contains("NULL AS detail_body");
        assertThat(sql).contains("NULL AS banner_image_url");
    }
}
