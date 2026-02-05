package com.bsl.search.service.grouping;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.grouping")
public class MaterialGroupingProperties {
    private boolean enabled = false;
    private boolean fillVariants = true;
    private List<String> titleStripTokens = new ArrayList<>();
    private List<String> recoverTokens = new ArrayList<>();
    private List<String> setTokens = new ArrayList<>();
    private List<String> specialTokens = new ArrayList<>();
    private double recoverPenalty = 0.15;
    private double setPenalty = 0.2;
    private double specialPenalty = 0.1;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isFillVariants() {
        return fillVariants;
    }

    public void setFillVariants(boolean fillVariants) {
        this.fillVariants = fillVariants;
    }

    public List<String> getTitleStripTokens() {
        return titleStripTokens;
    }

    public void setTitleStripTokens(List<String> titleStripTokens) {
        this.titleStripTokens = titleStripTokens;
    }

    public List<String> getRecoverTokens() {
        return recoverTokens;
    }

    public void setRecoverTokens(List<String> recoverTokens) {
        this.recoverTokens = recoverTokens;
    }

    public List<String> getSetTokens() {
        return setTokens;
    }

    public void setSetTokens(List<String> setTokens) {
        this.setTokens = setTokens;
    }

    public List<String> getSpecialTokens() {
        return specialTokens;
    }

    public void setSpecialTokens(List<String> specialTokens) {
        this.specialTokens = specialTokens;
    }

    public double getRecoverPenalty() {
        return recoverPenalty;
    }

    public void setRecoverPenalty(double recoverPenalty) {
        this.recoverPenalty = recoverPenalty;
    }

    public double getSetPenalty() {
        return setPenalty;
    }

    public void setSetPenalty(double setPenalty) {
        this.setPenalty = setPenalty;
    }

    public double getSpecialPenalty() {
        return specialPenalty;
    }

    public void setSpecialPenalty(double specialPenalty) {
        this.specialPenalty = specialPenalty;
    }
}
