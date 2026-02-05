package com.bsl.ranking.features;

import java.util.List;
import java.util.Map;

public interface FeatureStoreClient {
    Map<String, Map<String, Object>> fetch(List<String> docIds);
}
