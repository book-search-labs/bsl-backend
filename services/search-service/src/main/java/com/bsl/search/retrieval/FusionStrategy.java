package com.bsl.search.retrieval;

import com.bsl.search.merge.RrfFusion;
import java.util.List;
import java.util.Map;

public interface FusionStrategy {
    List<RrfFusion.Candidate> fuse(Map<String, Integer> lexRanks, Map<String, Integer> vecRanks, int k);
}
