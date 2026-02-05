package com.bsl.commerce.service;

import com.bsl.commerce.common.ApiException;
import com.bsl.commerce.common.JdbcUtils;
import com.bsl.commerce.config.CommerceProperties;
import com.bsl.commerce.repository.InventoryRepository;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository inventoryRepository;
    private final CommerceProperties properties;

    public InventoryService(InventoryRepository inventoryRepository, CommerceProperties properties) {
        this.inventoryRepository = inventoryRepository;
        this.properties = properties;
    }

    public Map<String, Object> getBalance(long skuId, Long sellerId) {
        long resolvedSellerId = sellerId == null ? properties.getInventory().getDefaultSellerId() : sellerId;
        Map<String, Object> balance = inventoryRepository.findBalance(skuId, resolvedSellerId);
        if (balance == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "inventory balance not found");
        }
        return balance;
    }

    @Transactional
    public InventoryResult reserve(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId
    ) {
        return applyMutation(skuId, sellerId, qty, idempotencyKey, refType, refId, "RESERVE");
    }

    @Transactional
    public InventoryResult release(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId
    ) {
        return applyMutation(skuId, sellerId, qty, idempotencyKey, refType, refId, "RELEASE");
    }

    @Transactional
    public InventoryResult deduct(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId
    ) {
        return applyMutation(skuId, sellerId, qty, idempotencyKey, refType, refId, "DEDUCT");
    }

    @Transactional
    public InventoryResult restock(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId
    ) {
        return applyMutation(skuId, sellerId, qty, idempotencyKey, refType, refId, "RESTOCK");
    }

    @Transactional
    public InventoryResult adjust(
        long skuId,
        long sellerId,
        int delta,
        String idempotencyKey,
        String refType,
        String refId,
        Long adminId
    ) {
        return applyMutation(skuId, sellerId, delta, idempotencyKey, refType, refId, "ADJUST", adminId);
    }

    public java.util.List<Map<String, Object>> listLedger(long skuId, long sellerId, int limit) {
        return inventoryRepository.listLedger(skuId, sellerId, limit);
    }

    private InventoryResult applyMutation(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId,
        String type
    ) {
        return applyMutation(skuId, sellerId, qty, idempotencyKey, refType, refId, type, null);
    }

    private InventoryResult applyMutation(
        long skuId,
        long sellerId,
        int qty,
        String idempotencyKey,
        String refType,
        String refId,
        String type,
        Long adminId
    ) {
        if (qty == 0) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty must be non-zero");
        }
        if (!"ADJUST".equals(type) && qty < 0) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "qty must be positive");
        }

        Map<String, Object> balance = inventoryRepository.findBalanceForUpdate(skuId, sellerId);
        if (balance == null) {
            if ("RESTOCK".equals(type) || "ADJUST".equals(type)) {
                inventoryRepository.insertBalance(skuId, sellerId);
                balance = inventoryRepository.findBalanceForUpdate(skuId, sellerId);
            } else {
                throw new ApiException(HttpStatus.NOT_FOUND, "not_found", "inventory balance not found");
            }
        }

        if (idempotencyKey != null) {
            Map<String, Object> existing = inventoryRepository.findLedgerByIdempotencyKey(idempotencyKey);
            if (existing != null) {
                return new InventoryResult(balance, existing, true);
            }
        }

        int onHand = JdbcUtils.asInt(balance.get("on_hand")) == null ? 0 : JdbcUtils.asInt(balance.get("on_hand"));
        int reserved = JdbcUtils.asInt(balance.get("reserved")) == null ? 0 : JdbcUtils.asInt(balance.get("reserved"));
        int available = JdbcUtils.asInt(balance.get("available")) == null ? (onHand - reserved)
            : JdbcUtils.asInt(balance.get("available"));

        int nextOnHand = onHand;
        int nextReserved = reserved;
        int delta = qty;

        switch (type) {
            case "RESERVE" -> {
                if (available < qty) {
                    throw new ApiException(HttpStatus.CONFLICT, "insufficient_stock", "insufficient stock");
                }
                nextReserved = reserved + qty;
            }
            case "RELEASE" -> {
                if (reserved < qty) {
                    throw new ApiException(HttpStatus.CONFLICT, "insufficient_reserved", "insufficient reserved stock");
                }
                nextReserved = reserved - qty;
            }
            case "DEDUCT" -> {
                if (reserved < qty) {
                    throw new ApiException(HttpStatus.CONFLICT, "insufficient_reserved", "insufficient reserved stock");
                }
                nextReserved = reserved - qty;
                nextOnHand = onHand - qty;
                if (nextOnHand < 0) {
                    throw new ApiException(HttpStatus.CONFLICT, "insufficient_stock", "insufficient stock");
                }
            }
            case "RESTOCK" -> {
                nextOnHand = onHand + qty;
            }
            case "ADJUST" -> {
                nextOnHand = onHand + qty;
                if (nextOnHand < 0) {
                    throw new ApiException(HttpStatus.CONFLICT, "insufficient_stock", "inventory cannot be negative");
                }
            }
            default -> throw new ApiException(HttpStatus.BAD_REQUEST, "bad_request", "unknown inventory operation");
        }

        inventoryRepository.updateBalance(skuId, sellerId, nextOnHand, nextReserved);

        Map<String, Object> ledgerRow = null;
        try {
            long ledgerId = inventoryRepository.insertLedger(
                skuId,
                sellerId,
                type,
                delta,
                idempotencyKey,
                refType,
                refId,
                null,
                adminId
            );
            if (ledgerId > 0) {
                ledgerRow = inventoryRepository.findLedgerByIdempotencyKey(idempotencyKey);
            }
        } catch (DuplicateKeyException ex) {
            ledgerRow = inventoryRepository.findLedgerByIdempotencyKey(idempotencyKey);
        }

        Map<String, Object> updated = inventoryRepository.findBalance(skuId, sellerId);
        return new InventoryResult(updated, ledgerRow, false);
    }

    public record InventoryResult(Map<String, Object> balance, Map<String, Object> ledger, boolean idempotent) {
    }
}
