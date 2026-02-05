package com.bsl.bff.budget;

import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
public class BudgetFilter extends OncePerRequestFilter {
    private final BudgetProperties properties;

    public BudgetFilter(BudgetProperties properties) {
        this.properties = properties;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (properties == null || !properties.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }

        RequestContext context = RequestContextHolder.get();
        long startedAtNs = context != null ? context.getStartedAtNs() : System.nanoTime();
        long budgetMs = resolveBudget(request.getRequestURI());
        BudgetContextHolder.set(new BudgetContext(startedAtNs, budgetMs));
        try {
            filterChain.doFilter(request, response);
        } finally {
            BudgetContextHolder.clear();
        }
    }

    private long resolveBudget(String path) {
        if (path == null) {
            return properties.getDefaultMs();
        }
        if (path.startsWith("/search")) {
            return properties.getSearchMs();
        }
        if (path.startsWith("/chat")) {
            return properties.getChatMs();
        }
        return properties.getDefaultMs();
    }
}
