package com.bsl.commerce.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;

import com.bsl.commerce.config.PaymentProperties;
import com.bsl.commerce.repository.LedgerRepository;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class LedgerServiceTest {

    @Mock
    private LedgerRepository ledgerRepository;

    @Test
    void recordPaymentCapturedWritesSaleAndFeesWithAvailabilityDelay() {
        PaymentProperties properties = new PaymentProperties();
        properties.setPgFeeRatePercent(3.0d);
        properties.setPlatformFeeRatePercent(10.0d);
        properties.setSettlementAvailableDelayDays(2);
        LedgerService service = new LedgerService(ledgerRepository, properties);

        service.recordPaymentCaptured(
            31L,
            11L,
            List.of(Map.of(
                "seller_id", 7L,
                "order_item_id", 101L,
                "qty", 2,
                "unit_price", 10000
            )),
            "KRW",
            "WEBHOOK_CAPTURE"
        );

        LocalDate expectedAvailableOn = LocalDate.now().plusDays(2);
        verify(ledgerRepository).insertEntry(
            eq(7L),
            eq(11L),
            eq(31L),
            eq("SALE"),
            eq(20000),
            eq("KRW"),
            any(),
            eq(expectedAvailableOn),
            eq("WEBHOOK_CAPTURE"),
            eq("payment:31:item:101:sale")
        );
        verify(ledgerRepository).insertEntry(
            eq(7L),
            eq(11L),
            eq(31L),
            eq("PG_FEE"),
            eq(-600),
            eq("KRW"),
            any(),
            eq(expectedAvailableOn),
            eq("WEBHOOK_CAPTURE"),
            eq("payment:31:item:101:pg_fee")
        );
        verify(ledgerRepository).insertEntry(
            eq(7L),
            eq(11L),
            eq(31L),
            eq("PLATFORM_FEE"),
            eq(-2000),
            eq("KRW"),
            any(),
            eq(expectedAvailableOn),
            eq("WEBHOOK_CAPTURE"),
            eq("payment:31:item:101:platform_fee")
        );
    }

    @Test
    void recordRefundWritesNegativeEntryAvailableSameDay() {
        PaymentProperties properties = new PaymentProperties();
        LedgerService service = new LedgerService(ledgerRepository, properties);

        service.recordRefund(
            501L,
            11L,
            31L,
            "KRW",
            List.of(Map.of("order_item_id", 101L, "amount", 12000)),
            Map.of(101L, 7L)
        );

        verify(ledgerRepository).insertEntry(
            eq(7L),
            eq(11L),
            eq(31L),
            eq("REFUND"),
            eq(-12000),
            eq("KRW"),
            any(),
            eq(LocalDate.now()),
            eq("REFUND_COMPLETE"),
            eq("refund:501:item:101:refund")
        );
    }
}
