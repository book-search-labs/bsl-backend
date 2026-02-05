package com.bsl.bff.security;

public class AuthContext {
    private final String userId;
    private final String adminId;

    public AuthContext(String userId, String adminId) {
        this.userId = userId;
        this.adminId = adminId;
    }

    public String getUserId() {
        return userId;
    }

    public String getAdminId() {
        return adminId;
    }

    public boolean isAdmin() {
        return adminId != null && !adminId.isBlank();
    }
}
