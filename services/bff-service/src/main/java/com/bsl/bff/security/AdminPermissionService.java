package com.bsl.bff.security;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class AdminPermissionService {
    private final AdminPermissionRepository repository;
    private final RbacProperties properties;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public AdminPermissionService(AdminPermissionRepository repository, RbacProperties properties) {
        this.repository = repository;
        this.properties = properties;
    }

    public boolean hasPermission(String adminId, String permission) {
        if (adminId == null || adminId.isBlank()) {
            return false;
        }
        Set<String> perms = loadPermissions(adminId);
        return perms.contains(permission);
    }

    private Set<String> loadPermissions(String adminId) {
        CacheEntry entry = cache.get(adminId);
        long now = Instant.now().toEpochMilli();
        if (entry != null && entry.expiresAt > now) {
            return entry.permissions;
        }
        Set<String> perms = repository.findPermissions(adminId);
        cache.put(adminId, new CacheEntry(perms, now + properties.getCacheTtlMs()));
        return perms;
    }

    private static class CacheEntry {
        private final Set<String> permissions;
        private final long expiresAt;

        private CacheEntry(Set<String> permissions, long expiresAt) {
            this.permissions = permissions;
            this.expiresAt = expiresAt;
        }
    }
}
