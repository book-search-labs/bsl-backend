package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.repository.PreorderRepository;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PreorderServiceTest {

    @Mock
    private PreorderRepository preorderRepository;

    @Test
    void resolveQueryDefaultsAndClamps() {
        PreorderService service = new PreorderService(preorderRepository);

        PreorderService.QueryOptions defaults = service.resolveQuery(null);
        PreorderService.QueryOptions clamped = service.resolveQuery(999);

        assertThat(defaults.limit()).isEqualTo(12);
        assertThat(clamped.limit()).isEqualTo(60);
    }

    @Test
    void reserveThrowsWhenLimitExceeded() {
        PreorderService service = new PreorderService(preorderRepository);

        when(preorderRepository.findActiveItemById(11L)).thenReturn(
            Map.of("preorder_id", 11L, "reservation_limit", 3, "preorder_price", 15000)
        );
        when(preorderRepository.findUserReservation(11L, 1L)).thenReturn(null);
        when(preorderRepository.countReservedQty(11L)).thenReturn(3);

        assertThatThrownBy(() -> service.reserve(1L, 11L, new PreorderService.ReserveRequest(1, null)))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> assertThat(((ApiException) error).getCode()).isEqualTo("preorder_limit_exceeded"));
    }

    @Test
    void reserveInsertsWhenNoExistingReservation() {
        PreorderService service = new PreorderService(preorderRepository);

        when(preorderRepository.findActiveItemById(11L)).thenReturn(
            Map.of("preorder_id", 11L, "reservation_limit", 5, "preorder_price", 15300)
        );
        when(preorderRepository.findUserReservation(11L, 1L)).thenReturn(null);
        when(preorderRepository.countReservedQty(11L)).thenReturn(2);
        when(preorderRepository.insertReservation(11L, 1L, 2, 15300, "빠른 수령")).thenReturn(77L);

        Map<String, Object> reservation = service.reserve(1L, 11L, new PreorderService.ReserveRequest(2, "빠른 수령"));

        assertThat(reservation.get("reservation_id")).isEqualTo(77L);
        assertThat(reservation.get("reserved_total")).isEqualTo(4);
        assertThat(reservation.get("remaining")).isEqualTo(1);
        verify(preorderRepository).insertReservation(11L, 1L, 2, 15300, "빠른 수령");
    }

    @Test
    void listActivePreordersMapsRows() {
        PreorderService service = new PreorderService(preorderRepository);
        when(preorderRepository.listActiveItems(1L, 12)).thenReturn(
            List.of(Map.of(
                "preorder_id", 9L,
                "material_id", "nlk:CDM200900003",
                "title_ko", "초등영어교육의 영미문화지도에 관한 연구",
                "author_name", "한은경",
                "preorder_price", 13300,
                "reserved_by_me", 1,
                "reserved_qty", 1
            ))
        );

        List<Map<String, Object>> items = service.listActivePreorders(1L, service.resolveQuery(null));
        assertThat(items).hasSize(1);
        assertThat(items.get(0).get("doc_id")).isEqualTo("nlk:CDM200900003");
        assertThat(items.get(0).get("reserved_by_me")).isEqualTo(true);
        assertThat(items.get(0).get("preorder_price_label")).isEqualTo("13,300원");
    }
}
