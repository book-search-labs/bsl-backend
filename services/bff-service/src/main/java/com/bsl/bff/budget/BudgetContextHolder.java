package com.bsl.bff.budget;

public final class BudgetContextHolder {
    private static final ThreadLocal<BudgetContext> HOLDER = new ThreadLocal<>();

    private BudgetContextHolder() {
    }

    public static void set(BudgetContext context) {
        HOLDER.set(context);
    }

    public static BudgetContext get() {
        return HOLDER.get();
    }

    public static void clear() {
        HOLDER.remove();
    }
}
