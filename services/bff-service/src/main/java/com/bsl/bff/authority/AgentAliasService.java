package com.bsl.bff.authority;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class AgentAliasService {
    private final AuthorityRepository repository;

    public AgentAliasService(AuthorityRepository repository) {
        this.repository = repository;
    }

    public List<String> applyAliases(List<String> names) {
        if (names == null || names.isEmpty()) {
            return names;
        }
        Set<String> unique = new HashSet<>();
        for (String name : names) {
            if (name != null && !name.isBlank()) {
                unique.add(name);
            }
        }
        if (unique.isEmpty()) {
            return names;
        }
        Map<String, String> mapping = repository.resolveAliases(new ArrayList<>(unique));
        if (mapping.isEmpty()) {
            return names;
        }
        List<String> result = new ArrayList<>(names.size());
        for (String name : names) {
            if (name == null) {
                result.add(null);
            } else {
                result.add(mapping.getOrDefault(name, name));
            }
        }
        return result;
    }
}
