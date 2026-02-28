package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class BffAuthLoginRequest {
    @JsonProperty("version")
    private String version;

    @JsonProperty("email")
    private String email;

    @JsonProperty("password")
    private String password;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
