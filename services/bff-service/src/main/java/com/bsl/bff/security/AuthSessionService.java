package com.bsl.bff.security;

import com.bsl.bff.common.UnauthorizedException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class AuthSessionService {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String DEFAULT_MEMBERSHIP_LABEL = "WELCOME";
    private static final String DEFAULT_PHONE = "010-0000-0000";

    private final UserAccountRepository userAccountRepository;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final AuthProperties properties;
    private final Map<String, SessionRecord> memorySessions = new ConcurrentHashMap<>();

    public AuthSessionService(
        UserAccountRepository userAccountRepository,
        ObjectProvider<StringRedisTemplate> redisTemplateProvider,
        ObjectMapper objectMapper,
        AuthProperties properties
    ) {
        this.userAccountRepository = userAccountRepository;
        this.redisTemplate = redisTemplateProvider.getIfAvailable();
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public SessionRecord login(String email, String password) {
        String normalizedEmail = normalizeEmail(email);
        String rawPassword = password == null ? "" : password;

        UserAccountRepository.UserAccount account = userAccountRepository.findActiveByEmail(normalizedEmail)
            .orElseThrow(() -> new UnauthorizedException("이메일 또는 비밀번호가 올바르지 않습니다."));

        if (!verifyPassword(rawPassword, account.passwordHash())) {
            throw new UnauthorizedException("이메일 또는 비밀번호가 올바르지 않습니다.");
        }

        long now = System.currentTimeMillis();
        SessionRecord session = new SessionRecord(
            newSessionId(),
            account.userId(),
            fallback(account.email(), normalizedEmail),
            fallback(account.name(), "BSL 회원"),
            DEFAULT_MEMBERSHIP_LABEL,
            fallback(account.phone(), DEFAULT_PHONE),
            now + Math.max(60, properties.getSessionTtlSeconds()) * 1000L
        );
        saveSession(session);
        userAccountRepository.updateLastLogin(account.userId());
        return session;
    }

    public Optional<SessionRecord> getSession(String sessionId) {
        String normalized = normalizeSessionId(sessionId);
        if (normalized == null) {
            return Optional.empty();
        }

        Optional<SessionRecord> fromRedis = readSessionFromRedis(normalized);
        if (fromRedis.isPresent()) {
            return fromRedis;
        }

        SessionRecord cached = memorySessions.get(normalized);
        if (cached == null) {
            return Optional.empty();
        }
        if (isExpired(cached)) {
            memorySessions.remove(normalized);
            return Optional.empty();
        }
        return Optional.of(cached);
    }

    public void logout(String sessionId) {
        String normalized = normalizeSessionId(sessionId);
        if (normalized == null) {
            return;
        }
        deleteSessionFromRedis(normalized);
        memorySessions.remove(normalized);
    }

    private void saveSession(SessionRecord session) {
        memorySessions.put(session.sessionId(), session);

        if (redisTemplate == null) {
            return;
        }
        try {
            String key = redisKey(session.sessionId());
            String value = objectMapper.writeValueAsString(session);
            redisTemplate.opsForValue().set(
                key,
                value,
                Duration.ofSeconds(Math.max(60, properties.getSessionTtlSeconds()))
            );
        } catch (Exception ignored) {
            // keep in-memory fallback session
        }
    }

    private Optional<SessionRecord> readSessionFromRedis(String sessionId) {
        if (redisTemplate == null) {
            return Optional.empty();
        }
        try {
            String raw = redisTemplate.opsForValue().get(redisKey(sessionId));
            if (raw == null || raw.isBlank()) {
                return Optional.empty();
            }
            SessionRecord session = objectMapper.readValue(raw, SessionRecord.class);
            if (isExpired(session)) {
                deleteSessionFromRedis(sessionId);
                return Optional.empty();
            }
            return Optional.of(session);
        } catch (Exception ignored) {
            return Optional.empty();
        }
    }

    private void deleteSessionFromRedis(String sessionId) {
        if (redisTemplate == null) {
            return;
        }
        try {
            redisTemplate.delete(redisKey(sessionId));
        } catch (Exception ignored) {
            // ignore redis delete failures
        }
    }

    private String redisKey(String sessionId) {
        return properties.getSessionKeyPrefix() + sessionId;
    }

    private boolean isExpired(SessionRecord session) {
        return session == null || session.expiresAtMs() <= System.currentTimeMillis();
    }

    private String normalizeSessionId(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.isEmpty()) {
            return null;
        }
        return trimmed;
    }

    private String normalizeEmail(String value) {
        if (value == null) {
            return "";
        }
        return value.trim().toLowerCase();
    }

    private String fallback(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value;
    }

    private String newSessionId() {
        byte[] bytes = new byte[24];
        RANDOM.nextBytes(bytes);
        return "sess_" + HexFormat.of().formatHex(bytes);
    }

    private boolean verifyPassword(String rawPassword, String storedHash) {
        if (storedHash == null || storedHash.isBlank()) {
            return false;
        }
        String normalizedStored = storedHash.trim();
        if (normalizedStored.startsWith("sha256:")) {
            String expected = normalizedStored.substring("sha256:".length()).trim();
            return sha256(rawPassword).equalsIgnoreCase(expected);
        }
        return normalizedStored.equals(rawPassword);
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hashed);
        } catch (Exception ex) {
            return "";
        }
    }

    public record SessionRecord(
        String sessionId,
        long userId,
        String email,
        String name,
        String membershipLabel,
        String phone,
        long expiresAtMs
    ) {
    }
}
