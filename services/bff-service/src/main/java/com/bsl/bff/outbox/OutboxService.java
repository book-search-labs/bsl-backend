package com.bsl.bff.outbox;

import com.bsl.bff.config.OutboxProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

@Service
public class OutboxService {
    private static final Logger logger = LoggerFactory.getLogger(OutboxService.class);

    private final OutboxEventRepository repository;
    private final ObjectMapper objectMapper;
    private final OutboxProperties properties;

    public OutboxService(OutboxEventRepository repository, ObjectMapper objectMapper, OutboxProperties properties) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public void record(String eventType, String aggregateType, String aggregateId, Object payload) {
        if (!properties.isEnabled()) {
            return;
        }
        String dedupKey = sha256(eventType + ":" + aggregateId);
        String payloadJson = toJson(payload);
        if (payloadJson == null) {
            return;
        }
        OutboxEvent event = new OutboxEvent(
            eventType,
            aggregateType,
            aggregateId,
            dedupKey,
            payloadJson,
            "NEW"
        );
        try {
            repository.insert(event);
        } catch (DuplicateKeyException ex) {
            logger.debug("Outbox event already exists: {}", dedupKey);
        } catch (Exception ex) {
            logger.warn("Failed to persist outbox event {}: {}", eventType, ex.getMessage());
        }
    }

    private String toJson(Object payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException ex) {
            logger.warn("Failed to serialize outbox payload: {}", ex.getMessage());
            return null;
        }
    }

    private String sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 not available", ex);
        }
    }
}
