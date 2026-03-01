package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.LedgerRepository;
import com.bsl.commerce.repository.SettlementRepository;
import io.micrometer.core.instrument.Metrics;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SettlementService {
    private static final Logger logger = LoggerFactory.getLogger(SettlementService.class);

    private final SettlementRepository settlementRepository;
    private final LedgerRepository ledgerRepository;

    public SettlementService(SettlementRepository settlementRepository, LedgerRepository ledgerRepository) {
        this.settlementRepository = settlementRepository;
        this.ledgerRepository = ledgerRepository;
    }

    @Transactional
    public Map<String, Object> createCycle(LocalDate startDate, LocalDate endDate) {
        if (startDate == null || endDate == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "start_date, end_date는 필수입니다.");
        }
        if (endDate.isBefore(startDate)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "end_date는 start_date보다 빠를 수 없습니다.");
        }

        Map<String, Object> existing = settlementRepository.findCycleByPeriod(startDate, endDate);
        if (existing != null) {
            throw new ApiException(HttpStatus.CONFLICT, "duplicate_cycle", "동일 기간의 정산 사이클이 이미 존재합니다.");
        }

        long cycleId = settlementRepository.insertCycle(startDate, endDate, "GENERATED");
        List<Map<String, Object>> aggregates = ledgerRepository.aggregateSellerLines(startDate, endDate);
        for (Map<String, Object> row : aggregates) {
            long sellerId = JdbcUtils.asLong(row.get("seller_id"));
            int gross = JdbcUtils.asInt(row.get("gross_sales")) == null ? 0 : JdbcUtils.asInt(row.get("gross_sales"));
            int fees = JdbcUtils.asInt(row.get("total_fees")) == null ? 0 : JdbcUtils.asInt(row.get("total_fees"));
            int net = gross + fees;
            settlementRepository.insertLine(cycleId, sellerId, gross, fees, net, "UNPAID");
        }
        Metrics.counter("commerce.settlement.cycles.total", "outcome", "generated").increment();
        Metrics.counter("commerce.settlement.lines.total", "outcome", "generated").increment(aggregates.size());
        logger.info(
            "settlement_cycle_generated cycle_id={} start_date={} end_date={} seller_lines={}",
            cycleId,
            startDate,
            endDate,
            aggregates.size()
        );

        return getCycleDetail(cycleId);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listCycles(int limit, String status, String fromDate, String toDate) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        LocalDate from = parseLocalDateOrNull(fromDate, "from");
        LocalDate to = parseLocalDateOrNull(toDate, "to");
        if (from != null && to != null && to.isBefore(from)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "to 날짜는 from 날짜보다 빠를 수 없습니다.");
        }
        return settlementRepository.listCycles(resolved, trimToNull(status), from, to);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getCycleDetail(long cycleId) {
        Map<String, Object> cycle = requireCycle(cycleId);
        List<Map<String, Object>> lines = settlementRepository.listLines(cycleId);
        Map<String, Object> result = new HashMap<>();
        result.put("cycle", cycle);
        result.put("lines", lines);
        result.put("count", lines.size());
        return result;
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listLines(long cycleId) {
        requireCycle(cycleId);
        return settlementRepository.listLines(cycleId);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listPayouts(int limit, String status) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        return settlementRepository.listPayouts(resolved, trimToNull(status));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> listReconciliationMismatches(int limit, String fromDate, String toDate) {
        int resolved = Math.min(Math.max(limit, 1), 200);
        LocalDate from = parseLocalDateOrNull(fromDate, "from");
        LocalDate to = parseLocalDateOrNull(toDate, "to");
        if (from != null && to != null && to.isBefore(from)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "to 날짜는 from 날짜보다 빠를 수 없습니다.");
        }
        List<Map<String, Object>> items = settlementRepository.listReconciliationMismatches(resolved, from, to);
        Map<String, Object> result = new HashMap<>();
        result.put("items", items);
        result.put("count", items.size());
        result.put("from", from == null ? null : from.toString());
        result.put("to", to == null ? null : to.toString());
        return result;
    }

    @Transactional
    public Map<String, Object> runPayouts(long cycleId) {
        Map<String, Object> cycle = requireCycle(cycleId);
        String status = JdbcUtils.asString(cycle.get("status"));
        if ("PAID".equals(status)) {
            Map<String, Object> result = new HashMap<>();
            result.put("cycle", cycle);
            result.put("payouts", settlementRepository.listPayoutsByCycle(cycleId));
            Metrics.counter("commerce.settlement.payout.total", "outcome", "skip_already_paid").increment();
            logger.info("settlement_payout_skip_already_paid cycle_id={}", cycleId);
            return result;
        }

        List<Map<String, Object>> targetLines = settlementRepository.listLinesForPayout(cycleId);
        int paidCount = 0;
        int failedCount = 0;
        for (Map<String, Object> line : targetLines) {
            long lineId = JdbcUtils.asLong(line.get("settlement_line_id"));
            int netAmount = JdbcUtils.asInt(line.get("net_amount")) == null ? 0 : JdbcUtils.asInt(line.get("net_amount"));
            settlementRepository.insertPayout(lineId, "SCHEDULED");
            if (netAmount > 0) {
                settlementRepository.updatePayoutStatus(lineId, "PAID", null);
                settlementRepository.updateLineStatus(lineId, "PAID");
                paidCount++;
            } else {
                settlementRepository.updatePayoutStatus(lineId, "FAILED", "non_positive_net_amount");
                settlementRepository.updateLineStatus(lineId, "FAILED");
                failedCount++;
            }
        }
        Metrics.counter("commerce.settlement.payout.total", "outcome", "attempted").increment(targetLines.size());
        if (paidCount > 0) {
            Metrics.counter("commerce.settlement.payout.total", "outcome", "paid").increment(paidCount);
        }
        if (failedCount > 0) {
            Metrics.counter("commerce.settlement.payout.total", "outcome", "failed").increment(failedCount);
        }

        String nextCycleStatus = refreshCycleStatus(cycleId);
        Metrics.counter("commerce.settlement.cycle.status.total", "status", nextCycleStatus).increment();
        int failed = settlementRepository.countLinesByStatus(cycleId, "FAILED");
        int unpaid = settlementRepository.countLinesByStatus(cycleId, "UNPAID");
        logger.info(
            "settlement_payout_result cycle_id={} target_lines={} paid_lines={} failed_lines={} unpaid_lines={} cycle_status={}",
            cycleId,
            targetLines.size(),
            paidCount,
            failed,
            unpaid,
            nextCycleStatus
        );

        Map<String, Object> refreshedCycle = requireCycle(cycleId);
        Map<String, Object> result = new HashMap<>();
        result.put("cycle", refreshedCycle);
        result.put("payouts", settlementRepository.listPayoutsByCycle(cycleId));
        return result;
    }

    @Transactional
    public Map<String, Object> retryPayout(long payoutId) {
        Map<String, Object> payout = settlementRepository.findPayoutById(payoutId);
        if (payout == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "정산 지급 정보를 찾을 수 없습니다.");
        }

        long cycleId = JdbcUtils.asLong(payout.get("cycle_id"));
        long settlementLineId = JdbcUtils.asLong(payout.get("settlement_line_id"));
        String payoutStatus = JdbcUtils.asString(payout.get("status"));
        int netAmount = JdbcUtils.asInt(payout.get("net_amount")) == null ? 0 : JdbcUtils.asInt(payout.get("net_amount"));

        String retryOutcome = "already_paid";
        if (!"PAID".equals(payoutStatus)) {
            if (netAmount > 0) {
                settlementRepository.updatePayoutStatus(settlementLineId, "PAID", null);
                settlementRepository.updateLineStatus(settlementLineId, "PAID");
                retryOutcome = "paid";
            } else {
                settlementRepository.updatePayoutStatus(settlementLineId, "FAILED", "non_positive_net_amount");
                settlementRepository.updateLineStatus(settlementLineId, "FAILED");
                retryOutcome = "failed_non_positive_net_amount";
            }
        }

        String cycleStatus = refreshCycleStatus(cycleId);
        Metrics.counter("commerce.settlement.cycle.status.total", "status", cycleStatus).increment();
        Metrics.counter("commerce.settlement.payout.retry.total", "outcome", retryOutcome).increment();
        if ("paid".equals(retryOutcome)) {
            Metrics.counter("commerce.settlement.payout.total", "outcome", "paid").increment();
        }
        logger.info(
            "settlement_payout_retry payout_id={} cycle_id={} settlement_line_id={} outcome={} cycle_status={}",
            payoutId,
            cycleId,
            settlementLineId,
            retryOutcome,
            cycleStatus
        );

        Map<String, Object> result = new HashMap<>();
        result.put("cycle", requireCycle(cycleId));
        result.put("payout", settlementRepository.findPayoutById(payoutId));
        result.put("payouts", settlementRepository.listPayoutsByCycle(cycleId));
        return result;
    }

    private Map<String, Object> requireCycle(long cycleId) {
        Map<String, Object> cycle = settlementRepository.findCycleById(cycleId);
        if (cycle == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "정산 사이클을 찾을 수 없습니다.");
        }
        return cycle;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private LocalDate parseLocalDateOrNull(String value, String fieldName) {
        String trimmed = trimToNull(value);
        if (trimmed == null) {
            return null;
        }
        try {
            return LocalDate.parse(trimmed);
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", fieldName + " 날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)");
        }
    }

    private String refreshCycleStatus(long cycleId) {
        int failed = settlementRepository.countLinesByStatus(cycleId, "FAILED");
        int unpaid = settlementRepository.countLinesByStatus(cycleId, "UNPAID");
        String nextCycleStatus;
        if (failed > 0) {
            nextCycleStatus = "FAILED";
        } else if (unpaid == 0) {
            nextCycleStatus = "PAID";
        } else {
            nextCycleStatus = "GENERATED";
        }
        settlementRepository.updateCycleStatus(cycleId, nextCycleStatus);
        return nextCycleStatus;
    }
}
