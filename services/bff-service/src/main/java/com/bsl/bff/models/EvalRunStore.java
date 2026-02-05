package com.bsl.bff.models;

import com.bsl.bff.config.ModelOpsProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;

@Service
public class EvalRunStore {
    private final ObjectMapper objectMapper;
    private final ModelOpsProperties properties;

    public EvalRunStore(ObjectMapper objectMapper, ModelOpsProperties properties) {
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public List<EvalRunReport> listRuns(int limit) {
        Path dir = Path.of(properties.getEvalRunsDir());
        if (!Files.exists(dir) || !Files.isDirectory(dir)) {
            return List.of();
        }
        try (Stream<Path> stream = Files.list(dir)) {
            return stream
                .filter(path -> path.toString().endsWith(".json"))
                .sorted(Comparator.comparingLong(this::mtime).reversed())
                .limit(limit)
                .map(this::readReport)
                .filter(report -> report != null)
                .collect(Collectors.toList());
        } catch (IOException ex) {
            return List.of();
        }
    }

    private long mtime(Path path) {
        try {
            return Files.getLastModifiedTime(path).toMillis();
        } catch (IOException ex) {
            return 0L;
        }
    }

    private EvalRunReport readReport(Path path) {
        try {
            return objectMapper.readValue(path.toFile(), EvalRunReport.class);
        } catch (Exception ex) {
            return null;
        }
    }
}
