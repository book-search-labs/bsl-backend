package com.bsl.bff.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.auth")
public class AuthProperties {
    private boolean enabled = true;
    private boolean bypass = false;
    private String adminHeader = "x-admin-id";
    private String userHeader = "x-user-id";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isBypass() {
        return bypass;
    }

    public void setBypass(boolean bypass) {
        this.bypass = bypass;
    }

    public String getAdminHeader() {
        return adminHeader;
    }

    public void setAdminHeader(String adminHeader) {
        this.adminHeader = adminHeader;
    }

    public String getUserHeader() {
        return userHeader;
    }

    public void setUserHeader(String userHeader) {
        this.userHeader = userHeader;
    }
}
