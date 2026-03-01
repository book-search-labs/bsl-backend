package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.HomePanelRepository;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class HomePanelServiceTest {

    @Mock
    private HomePanelRepository homePanelRepository;

    @Test
    void resolveQueryDefaultsToThirtyOne() {
        HomePanelService service = new HomePanelService(homePanelRepository);

        HomePanelService.QueryOptions options = service.resolveQuery(null, null);

        assertThat(options.limit()).isEqualTo(31);
        assertThat(options.panelType()).isNull();
    }

    @Test
    void listActivePanelsNormalizesTypeAndClampsLimit() {
        HomePanelService service = new HomePanelService(homePanelRepository);
        HomePanelService.QueryOptions options = service.resolveQuery(999, "event");

        when(homePanelRepository.listActiveItems("EVENT", 100)).thenReturn(List.of(Map.of("item_id", 1L)));
        when(homePanelRepository.countActiveItems("EVENT")).thenReturn(31L);

        List<Map<String, Object>> items = service.listActivePanels(options);
        long totalCount = service.countActivePanels(options);

        assertThat(items).hasSize(1);
        assertThat(totalCount).isEqualTo(31L);
        verify(homePanelRepository).listActiveItems("EVENT", 100);
        verify(homePanelRepository).countActiveItems("EVENT");
    }

    @Test
    void resolveQueryRejectsUnsupportedType() {
        HomePanelService service = new HomePanelService(homePanelRepository);

        assertThatThrownBy(() -> service.resolveQuery(31, "promotion"))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("EVENT or NOTICE");
    }

    @Test
    void getActivePanelReturnsNotFoundWhenMissing() {
        HomePanelService service = new HomePanelService(homePanelRepository);
        when(homePanelRepository.findActiveItemById(999L)).thenReturn(null);

        assertThatThrownBy(() -> service.getActivePanel(999L))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("home panel item not found");
    }
}
