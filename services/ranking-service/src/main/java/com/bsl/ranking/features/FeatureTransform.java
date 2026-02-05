package com.bsl.ranking.features;

import java.util.List;

public class FeatureTransform {
    private final Object defaultValue;
    private final Double clipMin;
    private final Double clipMax;
    private final boolean log1p;
    private final List<Double> bucketize;

    public FeatureTransform(Object defaultValue, Double clipMin, Double clipMax, boolean log1p, List<Double> bucketize) {
        this.defaultValue = defaultValue;
        this.clipMin = clipMin;
        this.clipMax = clipMax;
        this.log1p = log1p;
        this.bucketize = bucketize;
    }

    public Object getDefaultValue() {
        return defaultValue;
    }

    public Double getClipMin() {
        return clipMin;
    }

    public Double getClipMax() {
        return clipMax;
    }

    public boolean isLog1p() {
        return log1p;
    }

    public List<Double> getBucketize() {
        return bucketize;
    }
}
