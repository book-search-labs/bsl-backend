package com.bsl.bff.budget;

public class BudgetContext {
    private final long startedAtNs;
    private final long budgetMs;
    private final long deadlineNs;

    public BudgetContext(long startedAtNs, long budgetMs) {
        this.startedAtNs = startedAtNs;
        this.budgetMs = budgetMs;
        this.deadlineNs = startedAtNs + (budgetMs * 1_000_000L);
    }

    public long getBudgetMs() {
        return budgetMs;
    }

    public long remainingMs() {
        long remainingNs = deadlineNs - System.nanoTime();
        return Math.max(0L, remainingNs / 1_000_000L);
    }

    public boolean isExceeded() {
        return System.nanoTime() > deadlineNs;
    }
}
