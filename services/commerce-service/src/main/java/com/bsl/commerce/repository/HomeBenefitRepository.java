package com.bsl.commerce.repository;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HomeBenefitRepository {
    private static final String TABLE_NAME = "cart_content_item";
    private static final String COLUMN_BENEFIT_CODE = "benefit_code";
    private static final String COLUMN_BADGE = "badge";
    private static final String COLUMN_DISCOUNT_TYPE = "discount_type";
    private static final String COLUMN_DISCOUNT_VALUE = "discount_value";
    private static final String COLUMN_MIN_ORDER_AMOUNT = "min_order_amount";
    private static final String COLUMN_MAX_DISCOUNT_AMOUNT = "max_discount_amount";
    private static final String COLUMN_VALID_FROM = "valid_from";
    private static final String COLUMN_VALID_TO = "valid_to";
    private static final String COLUMN_DAILY_LIMIT = "daily_limit";
    private static final String COLUMN_REMAINING_DAILY = "remaining_daily";
    private static final String COLUMN_LINK_URL = "link_url";
    private static final String COLUMN_CTA_LABEL = "cta_label";

    private final JdbcTemplate jdbcTemplate;
    private volatile ColumnSupport columnSupport;

    public HomeBenefitRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> listTodayBenefits(int limit) {
        ColumnSupport support = resolveColumnSupport();
        if (!support.tableExists) {
            return List.of();
        }

        String select = "SELECT item_id, content_type, title, description, "
            + nullableColumn(COLUMN_BENEFIT_CODE, support.benefitCode) + " AS benefit_code, "
            + nullableColumn(COLUMN_BADGE, support.badge) + " AS badge, "
            + nullableColumn(COLUMN_DISCOUNT_TYPE, support.discountType) + " AS discount_type, "
            + nullableColumn(COLUMN_DISCOUNT_VALUE, support.discountValue) + " AS discount_value, "
            + nullableColumn(COLUMN_MIN_ORDER_AMOUNT, support.minOrderAmount) + " AS min_order_amount, "
            + nullableColumn(COLUMN_MAX_DISCOUNT_AMOUNT, support.maxDiscountAmount) + " AS max_discount_amount, "
            + nullableColumn(COLUMN_VALID_FROM, support.validFrom) + " AS valid_from, "
            + nullableColumn(COLUMN_VALID_TO, support.validTo) + " AS valid_to, "
            + nullableColumn(COLUMN_DAILY_LIMIT, support.dailyLimit) + " AS daily_limit, "
            + nullableColumn(COLUMN_REMAINING_DAILY, support.remainingDaily) + " AS remaining_daily, "
            + nullableColumn(COLUMN_LINK_URL, support.linkUrl) + " AS link_url, "
            + nullableColumn(COLUMN_CTA_LABEL, support.ctaLabel) + " AS cta_label "
            + "FROM " + TABLE_NAME + " "
            + "WHERE content_type = 'PROMOTION' AND is_active = 1 ";

        StringBuilder sql = new StringBuilder(select);
        List<Object> params = new ArrayList<>();
        if (support.validFrom) {
            sql.append("AND (valid_from IS NULL OR valid_from <= CURRENT_TIMESTAMP) ");
        }
        if (support.validTo) {
            sql.append("AND (valid_to IS NULL OR valid_to >= CURRENT_TIMESTAMP) ");
        }
        if (support.remainingDaily) {
            sql.append("AND (remaining_daily IS NULL OR remaining_daily > 0) ");
        }
        sql.append("ORDER BY sort_order ASC, item_id ASC LIMIT ?");
        params.add(limit);
        return jdbcTemplate.queryForList(sql.toString(), params.toArray());
    }

    public long countTodayBenefits() {
        ColumnSupport support = resolveColumnSupport();
        if (!support.tableExists) {
            return 0L;
        }

        StringBuilder sql = new StringBuilder(
            "SELECT COUNT(*) FROM " + TABLE_NAME + " "
                + "WHERE content_type = 'PROMOTION' AND is_active = 1 "
        );
        if (support.validFrom) {
            sql.append("AND (valid_from IS NULL OR valid_from <= CURRENT_TIMESTAMP) ");
        }
        if (support.validTo) {
            sql.append("AND (valid_to IS NULL OR valid_to >= CURRENT_TIMESTAMP) ");
        }
        if (support.remainingDaily) {
            sql.append("AND (remaining_daily IS NULL OR remaining_daily > 0) ");
        }
        Long value = jdbcTemplate.queryForObject(sql.toString(), Long.class);
        return value == null ? 0L : value;
    }

    private ColumnSupport resolveColumnSupport() {
        ColumnSupport cached = columnSupport;
        if (cached != null) {
            return cached;
        }
        synchronized (this) {
            if (columnSupport != null) {
                return columnSupport;
            }
            boolean tableExists = tableExists(TABLE_NAME);
            columnSupport = new ColumnSupport(
                tableExists,
                tableExists && hasColumn(COLUMN_BENEFIT_CODE),
                tableExists && hasColumn(COLUMN_BADGE),
                tableExists && hasColumn(COLUMN_DISCOUNT_TYPE),
                tableExists && hasColumn(COLUMN_DISCOUNT_VALUE),
                tableExists && hasColumn(COLUMN_MIN_ORDER_AMOUNT),
                tableExists && hasColumn(COLUMN_MAX_DISCOUNT_AMOUNT),
                tableExists && hasColumn(COLUMN_VALID_FROM),
                tableExists && hasColumn(COLUMN_VALID_TO),
                tableExists && hasColumn(COLUMN_DAILY_LIMIT),
                tableExists && hasColumn(COLUMN_REMAINING_DAILY),
                tableExists && hasColumn(COLUMN_LINK_URL),
                tableExists && hasColumn(COLUMN_CTA_LABEL)
            );
            return columnSupport;
        }
    }

    private boolean tableExists(String tableName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.tables "
                    + "WHERE table_schema = DATABASE() AND table_name = ?",
                Integer.class,
                tableName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }

    private boolean hasColumn(String columnName) {
        try {
            Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM information_schema.columns "
                    + "WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
                Integer.class,
                TABLE_NAME,
                columnName
            );
            return count != null && count > 0;
        } catch (Exception ex) {
            return false;
        }
    }

    private String nullableColumn(String columnName, boolean supported) {
        return supported ? columnName : "NULL";
    }

    private static final class ColumnSupport {
        private final boolean tableExists;
        private final boolean benefitCode;
        private final boolean badge;
        private final boolean discountType;
        private final boolean discountValue;
        private final boolean minOrderAmount;
        private final boolean maxDiscountAmount;
        private final boolean validFrom;
        private final boolean validTo;
        private final boolean dailyLimit;
        private final boolean remainingDaily;
        private final boolean linkUrl;
        private final boolean ctaLabel;

        private ColumnSupport(
            boolean tableExists,
            boolean benefitCode,
            boolean badge,
            boolean discountType,
            boolean discountValue,
            boolean minOrderAmount,
            boolean maxDiscountAmount,
            boolean validFrom,
            boolean validTo,
            boolean dailyLimit,
            boolean remainingDaily,
            boolean linkUrl,
            boolean ctaLabel
        ) {
            this.tableExists = tableExists;
            this.benefitCode = benefitCode;
            this.badge = badge;
            this.discountType = discountType;
            this.discountValue = discountValue;
            this.minOrderAmount = minOrderAmount;
            this.maxDiscountAmount = maxDiscountAmount;
            this.validFrom = validFrom;
            this.validTo = validTo;
            this.dailyLimit = dailyLimit;
            this.remainingDaily = remainingDaily;
            this.linkUrl = linkUrl;
            this.ctaLabel = ctaLabel;
        }
    }
}
