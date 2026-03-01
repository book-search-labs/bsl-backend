package com.bsl.bff.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.auth")
public class AuthProperties {
    private boolean enabled = true;
    private boolean bypass = false;
    private String adminHeader = "x-admin-id";
    private String userHeader = "x-user-id";
    private String sessionHeader = "x-session-id";
    private int sessionTtlSeconds = 86400;
    private String sessionKeyPrefix = "bff:session:";
    private boolean enforceUserApi = true;
    private String userApiPrefix = "/api/v1/";

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

    public String getSessionHeader() {
        return sessionHeader;
    }

    public void setSessionHeader(String sessionHeader) {
        this.sessionHeader = sessionHeader;
    }

    public int getSessionTtlSeconds() {
        return sessionTtlSeconds;
    }

    public void setSessionTtlSeconds(int sessionTtlSeconds) {
        this.sessionTtlSeconds = sessionTtlSeconds;
    }

    public String getSessionKeyPrefix() {
        return sessionKeyPrefix;
    }

    public void setSessionKeyPrefix(String sessionKeyPrefix) {
        this.sessionKeyPrefix = sessionKeyPrefix;
    }

    public boolean isEnforceUserApi() {
        return enforceUserApi;
    }

    public void setEnforceUserApi(boolean enforceUserApi) {
        this.enforceUserApi = enforceUserApi;
    }

    public String getUserApiPrefix() {
        return userApiPrefix;
    }

    public void setUserApiPrefix(String userApiPrefix) {
        this.userApiPrefix = userApiPrefix;
    }
}
