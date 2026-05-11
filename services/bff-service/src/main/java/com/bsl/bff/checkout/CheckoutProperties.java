package com.bsl.bff.checkout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bff.checkout")
public class CheckoutProperties {
    private String backend = "orchestrator";

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
    }

    public boolean useLegacy() {
        return "legacy".equalsIgnoreCase(backend);
    }
}
