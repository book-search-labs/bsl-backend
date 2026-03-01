package com.bsl.commerce.service;

import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.repository.HomeBenefitRepository;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class HomeBenefitService {
    private static final int DEFAULT_LIMIT = 12;
    private static final int MAX_LIMIT = 50;
    private static final NumberFormat KOREA_NUMBER = NumberFormat.getNumberInstance(Locale.KOREA);

    private final HomeBenefitRepository homeBenefitRepository;

    public HomeBenefitService(HomeBenefitRepository homeBenefitRepository) {
        this.homeBenefitRepository = homeBenefitRepository;
    }

    public QueryOptions resolveQuery(Integer limit) {
        int resolvedLimit = limit == null ? DEFAULT_LIMIT : Math.min(Math.max(limit, 1), MAX_LIMIT);
        return new QueryOptions(resolvedLimit);
    }

    public List<Map<String, Object>> listTodayBenefits(QueryOptions options) {
        return homeBenefitRepository.listTodayBenefits(options.limit()).stream()
            .map(this::toBenefit)
            .toList();
    }

    public long countTodayBenefits() {
        return homeBenefitRepository.countTodayBenefits();
    }

    public String resolveTodayDate() {
        return LocalDate.now().toString();
    }

    private Map<String, Object> toBenefit(Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        Integer discountValue = JdbcUtils.asInt(row.get("discount_value"));
        Integer minOrderAmount = JdbcUtils.asInt(row.get("min_order_amount"));
        Integer maxDiscountAmount = JdbcUtils.asInt(row.get("max_discount_amount"));
        String discountType = JdbcUtils.asString(row.get("discount_type"));

        item.put("item_id", JdbcUtils.asLong(row.get("item_id")));
        item.put("benefit_code", JdbcUtils.asString(row.get("benefit_code")));
        item.put("badge", JdbcUtils.asString(row.get("badge")));
        item.put("title", JdbcUtils.asString(row.get("title")));
        item.put("description", JdbcUtils.asString(row.get("description")));
        item.put("discount_type", discountType);
        item.put("discount_value", discountValue);
        item.put("discount_label", formatDiscountLabel(discountType, discountValue, maxDiscountAmount));
        item.put("min_order_amount", minOrderAmount);
        item.put("min_order_amount_label", formatCurrency(minOrderAmount));
        item.put("max_discount_amount", maxDiscountAmount);
        item.put("max_discount_amount_label", formatCurrency(maxDiscountAmount));
        item.put("valid_from", JdbcUtils.asIsoString(row.get("valid_from")));
        item.put("valid_to", JdbcUtils.asIsoString(row.get("valid_to")));
        item.put("daily_limit", JdbcUtils.asInt(row.get("daily_limit")));
        item.put("remaining_daily", JdbcUtils.asInt(row.get("remaining_daily")));
        item.put("link_url", JdbcUtils.asString(row.get("link_url")));
        item.put("cta_label", JdbcUtils.asString(row.get("cta_label")));
        return item;
    }

    private String formatDiscountLabel(String discountType, Integer discountValue, Integer maxDiscountAmount) {
        if (discountType == null || discountType.isBlank() || discountValue == null || discountValue <= 0) {
            return null;
        }
        return switch (discountType) {
            case "FIXED" -> formatCurrency(discountValue) + " 즉시 할인";
            case "PERCENT" -> {
                String percent = discountValue + "% 할인";
                if (maxDiscountAmount == null || maxDiscountAmount <= 0) {
                    yield percent;
                }
                yield percent + " (최대 " + formatCurrency(maxDiscountAmount) + ")";
            }
            default -> String.valueOf(discountValue);
        };
    }

    private String formatCurrency(Integer amount) {
        if (amount == null) {
            return null;
        }
        return KOREA_NUMBER.format(amount) + "원";
    }

    public record QueryOptions(int limit) {
    }
}
