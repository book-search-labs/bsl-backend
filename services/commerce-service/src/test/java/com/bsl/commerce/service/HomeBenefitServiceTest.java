package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.bsl.commerce.repository.HomeBenefitRepository;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class HomeBenefitServiceTest {

    @Mock
    private HomeBenefitRepository homeBenefitRepository;

    @Test
    void resolveQueryDefaultsAndClamps() {
        HomeBenefitService service = new HomeBenefitService(homeBenefitRepository);

        HomeBenefitService.QueryOptions defaults = service.resolveQuery(null);
        HomeBenefitService.QueryOptions clamped = service.resolveQuery(999);

        assertThat(defaults.limit()).isEqualTo(12);
        assertThat(clamped.limit()).isEqualTo(50);
    }

    @Test
    void listTodayBenefitsMapsDiscountLabels() {
        HomeBenefitService service = new HomeBenefitService(homeBenefitRepository);
        when(homeBenefitRepository.listTodayBenefits(12)).thenReturn(
            List.of(
                Map.of(
                    "item_id", 1L,
                    "title", "카카오페이 즉시할인",
                    "discount_type", "FIXED",
                    "discount_value", 4000,
                    "min_order_amount", 25000
                ),
                Map.of(
                    "item_id", 2L,
                    "title", "카드 할인",
                    "discount_type", "PERCENT",
                    "discount_value", 10,
                    "max_discount_amount", 12000
                )
            )
        );

        List<Map<String, Object>> items = service.listTodayBenefits(service.resolveQuery(null));
        assertThat(items).hasSize(2);
        assertThat(items.get(0).get("discount_label")).isEqualTo("4,000원 즉시 할인");
        assertThat(items.get(1).get("discount_label")).isEqualTo("10% 할인 (최대 12,000원)");
        assertThat(items.get(0).get("min_order_amount_label")).isEqualTo("25,000원");
    }
}
