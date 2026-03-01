package com.bsl.commerce.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bsl.commerce.repository.LedgerRepository;
import com.bsl.commerce.repository.SettlementRepository;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SettlementServiceTest {

    @Mock
    private SettlementRepository settlementRepository;

    @Mock
    private LedgerRepository ledgerRepository;

    @Test
    void createCycleAggregatesLedgerAndCreatesLines() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        LocalDate start = LocalDate.of(2026, 2, 1);
        LocalDate end = LocalDate.of(2026, 2, 28);

        when(settlementRepository.findCycleByPeriod(start, end)).thenReturn(null);
        when(settlementRepository.insertCycle(start, end, "GENERATED")).thenReturn(101L);
        when(ledgerRepository.aggregateSellerLines(start, end)).thenReturn(
            List.of(Map.of("seller_id", 7L, "gross_sales", 100000, "total_fees", -12000))
        );
        when(settlementRepository.findCycleById(101L)).thenReturn(Map.of("cycle_id", 101L, "status", "GENERATED"));
        when(settlementRepository.listLines(101L)).thenReturn(
            List.of(Map.of("cycle_id", 101L, "seller_id", 7L, "net_amount", 88000))
        );

        Map<String, Object> result = service.createCycle(start, end);

        assertThat(result).containsKey("cycle");
        verify(settlementRepository).insertLine(101L, 7L, 100000, -12000, 88000, "UNPAID");
    }

    @Test
    void runPayoutsMarksCyclePaidWhenAllLinesPaid() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        when(settlementRepository.findCycleById(202L)).thenReturn(
            Map.of("cycle_id", 202L, "status", "GENERATED"),
            Map.of("cycle_id", 202L, "status", "PAID")
        );
        when(settlementRepository.listLinesForPayout(202L)).thenReturn(
            List.of(Map.of("settlement_line_id", 301L, "net_amount", 50000))
        );
        when(settlementRepository.countLinesByStatus(202L, "FAILED")).thenReturn(0);
        when(settlementRepository.countLinesByStatus(202L, "UNPAID")).thenReturn(0);
        when(settlementRepository.listPayoutsByCycle(202L)).thenReturn(
            List.of(Map.of("settlement_line_id", 301L, "status", "PAID"))
        );

        Map<String, Object> result = service.runPayouts(202L);

        assertThat(result).containsKey("cycle");
        verify(settlementRepository).insertPayout(301L, "SCHEDULED");
        verify(settlementRepository).updatePayoutStatus(301L, "PAID", null);
        verify(settlementRepository).updateLineStatus(301L, "PAID");
        verify(settlementRepository).updateCycleStatus(202L, "PAID");
    }

    @Test
    void listCyclesParsesFiltersAndDelegatesRepository() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        LocalDate from = LocalDate.of(2026, 2, 1);
        LocalDate to = LocalDate.of(2026, 2, 28);
        when(settlementRepository.listCycles(50, "PAID", from, to)).thenReturn(
            List.of(Map.of("cycle_id", 999L, "status", "PAID"))
        );

        List<Map<String, Object>> result = service.listCycles(50, "PAID", "2026-02-01", "2026-02-28");

        assertThat(result).hasSize(1);
        verify(settlementRepository).listCycles(50, "PAID", from, to);
    }

    @Test
    void listCyclesRejectsInvalidDateRange() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        assertThatThrownBy(() -> service.listCycles(50, null, "2026-03-01", "2026-02-01"))
            .hasMessageContaining("to 날짜는 from 날짜보다 빠를 수 없습니다.");
    }

    @Test
    void retryPayoutMarksPaidWhenNetPositive() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        when(settlementRepository.findPayoutById(401L)).thenReturn(
            Map.of(
                "payout_id", 401L,
                "cycle_id", 202L,
                "settlement_line_id", 301L,
                "status", "FAILED",
                "net_amount", 50000
            ),
            Map.of(
                "payout_id", 401L,
                "cycle_id", 202L,
                "settlement_line_id", 301L,
                "status", "PAID",
                "net_amount", 50000
            )
        );
        when(settlementRepository.countLinesByStatus(202L, "FAILED")).thenReturn(0);
        when(settlementRepository.countLinesByStatus(202L, "UNPAID")).thenReturn(0);
        when(settlementRepository.findCycleById(202L)).thenReturn(Map.of("cycle_id", 202L, "status", "PAID"));
        when(settlementRepository.listPayoutsByCycle(202L)).thenReturn(
            List.of(Map.of("payout_id", 401L, "status", "PAID"))
        );

        Map<String, Object> result = service.retryPayout(401L);

        assertThat(result).containsKey("cycle");
        verify(settlementRepository).updatePayoutStatus(301L, "PAID", null);
        verify(settlementRepository).updateLineStatus(301L, "PAID");
        verify(settlementRepository).updateCycleStatus(202L, "PAID");
    }

    @Test
    void retryPayoutThrowsWhenNotFound() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);
        when(settlementRepository.findPayoutById(999L)).thenReturn(null);

        assertThatThrownBy(() -> service.retryPayout(999L))
            .hasMessageContaining("정산 지급 정보를 찾을 수 없습니다.");
    }

    @Test
    void listPayoutsDelegatesRepository() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);
        when(settlementRepository.listPayouts(200, "FAILED")).thenReturn(
            List.of(Map.of("payout_id", 1L, "status", "FAILED"))
        );

        List<Map<String, Object>> result = service.listPayouts(999, " FAILED ");

        assertThat(result).hasSize(1);
        verify(settlementRepository).listPayouts(200, "FAILED");
    }

    @Test
    void listReconciliationMismatchesDelegatesRepository() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);
        LocalDate from = LocalDate.of(2026, 2, 1);
        LocalDate to = LocalDate.of(2026, 2, 28);
        when(settlementRepository.listReconciliationMismatches(200, from, to)).thenReturn(
            List.of(Map.of("payment_id", 111L, "payment_amount", 12000, "sale_amount", 0))
        );

        Map<String, Object> result = service.listReconciliationMismatches(999, "2026-02-01", "2026-02-28");

        assertThat(result).containsEntry("count", 1);
        verify(settlementRepository).listReconciliationMismatches(200, from, to);
    }

    @Test
    void listReconciliationMismatchesRejectsInvalidDateRange() {
        SettlementService service = new SettlementService(settlementRepository, ledgerRepository);

        assertThatThrownBy(() -> service.listReconciliationMismatches(50, "2026-03-01", "2026-02-01"))
            .hasMessageContaining("to 날짜는 from 날짜보다 빠를 수 없습니다.");
    }
}
