package com.bsl.commerce.service;

import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.LoyaltyPointRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LoyaltyPointService {
    private final LoyaltyPointRepository loyaltyPointRepository;
    private final CommerceProperties properties;

    public LoyaltyPointService(
        LoyaltyPointRepository loyaltyPointRepository,
        CommerceProperties properties
    ) {
        this.loyaltyPointRepository = loyaltyPointRepository;
        this.properties = properties;
    }

    @Transactional(readOnly = true)
    public int getBalance(long userId) {
        return loyaltyPointRepository.getBalance(userId);
    }

    public int estimateEarnPoints(int amount) {
        if (amount <= 0) {
            return 0;
        }
        int rate = Math.max(properties.getLoyalty().getEarnRatePercent(), 0);
        return (amount * rate) / 100;
    }

    @Transactional
    public int earnForOrder(long userId, long orderId, int amount, String reason) {
        int points = estimateEarnPoints(amount);
        if (points <= 0) {
            return 0;
        }

        int current = loyaltyPointRepository.lockBalance(userId);
        if (loyaltyPointRepository.existsOrderLedger(orderId, "EARN")) {
            return current;
        }

        int next = current + points;
        loyaltyPointRepository.insertLedger(userId, orderId, "EARN", points, next, reason);
        loyaltyPointRepository.updateBalance(userId, next);
        return next;
    }
}
