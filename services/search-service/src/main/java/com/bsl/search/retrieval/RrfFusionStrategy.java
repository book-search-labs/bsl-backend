package com.bsl.search.retrieval;

import com.bsl.search.merge.RrfFusion;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class RrfFusionStrategy implements FusionStrategy {
    @Override
    public List<RrfFusion.Candidate> fuse(Map<String, Integer> lexRanks, Map<String, Integer> vecRanks, int k) {
        return RrfFusion.fuse(lexRanks, vecRanks, k);
    }
}
