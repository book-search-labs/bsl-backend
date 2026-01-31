package com.bsl.bff.models;

import com.bsl.bff.client.dto.MisModelInfo;
import com.bsl.bff.client.dto.MisModelsResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.config.ModelOpsProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ModelRegistryStore {
    private final ObjectMapper objectMapper;
    private final ModelOpsProperties properties;

    public ModelRegistryStore(ObjectMapper objectMapper, ModelOpsProperties properties) {
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public synchronized MisModelsResponse loadAsResponse(RequestContext context) {
        ModelRegistrySnapshot snapshot = loadSnapshot();
        List<MisModelInfo> models = new ArrayList<>();
        for (ModelRegistryEntry entry : snapshot.getModels()) {
            MisModelInfo info = new MisModelInfo();
            info.setId(entry.getId());
            info.setTask(entry.getTask());
            info.setBackend(entry.getBackend());
            info.setArtifactUri(entry.getArtifactUri());
            info.setActive(entry.getActive());
            info.setCanary(entry.getCanary());
            info.setCanaryWeight(entry.getCanaryWeight());
            info.setStatus(entry.getStatus());
            info.setLoaded(Boolean.FALSE);
            info.setUpdatedAt(entry.getUpdatedAt());
            models.add(info);
        }
        MisModelsResponse response = new MisModelsResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setModels(models);
        return response;
    }

    public synchronized void activate(String modelId, String task) {
        ModelRegistrySnapshot snapshot = loadSnapshot();
        ModelRegistryEntry target = findById(snapshot, modelId);
        if (task == null || task.isBlank()) {
            task = target.getTask();
        }
        String timestamp = Instant.now().toString();
        for (ModelRegistryEntry entry : snapshot.getModels()) {
            if (task.equals(entry.getTask())) {
                boolean isTarget = modelId.equals(entry.getId());
                entry.setActive(isTarget);
                if (isTarget) {
                    entry.setCanary(false);
                    entry.setCanaryWeight(0.0);
                }
                entry.setUpdatedAt(timestamp);
            }
        }
        snapshot.setUpdatedAt(timestamp);
        saveSnapshot(snapshot);
    }

    public synchronized void setCanary(String modelId, String task, double weight) {
        ModelRegistrySnapshot snapshot = loadSnapshot();
        ModelRegistryEntry target = findById(snapshot, modelId);
        if (task == null || task.isBlank()) {
            task = target.getTask();
        }
        double clamped = Math.max(0.0, Math.min(weight, 1.0));
        String timestamp = Instant.now().toString();
        for (ModelRegistryEntry entry : snapshot.getModels()) {
            if (task.equals(entry.getTask())) {
                boolean isTarget = modelId.equals(entry.getId());
                entry.setCanary(isTarget && clamped > 0.0);
                entry.setCanaryWeight(isTarget ? clamped : 0.0);
                entry.setUpdatedAt(timestamp);
            }
        }
        snapshot.setUpdatedAt(timestamp);
        saveSnapshot(snapshot);
    }

    private ModelRegistrySnapshot loadSnapshot() {
        Path path = Path.of(properties.getRegistryPath());
        if (!Files.exists(path)) {
            return new ModelRegistrySnapshot();
        }
        try {
            return objectMapper.readValue(path.toFile(), ModelRegistrySnapshot.class);
        } catch (Exception ex) {
            throw new BadRequestException("model_registry read failed");
        }
    }

    private void saveSnapshot(ModelRegistrySnapshot snapshot) {
        Path path = Path.of(properties.getRegistryPath());
        if (path.toFile().getParentFile() != null) {
            path.toFile().getParentFile().mkdirs();
        }
        try {
            objectMapper.writerWithDefaultPrettyPrinter().writeValue(path.toFile(), snapshot);
        } catch (Exception ex) {
            throw new BadRequestException("model_registry write failed");
        }
    }

    private ModelRegistryEntry findById(ModelRegistrySnapshot snapshot, String modelId) {
        if (modelId == null || modelId.isBlank()) {
            throw new BadRequestException("model_id is required");
        }
        for (ModelRegistryEntry entry : snapshot.getModels()) {
            if (modelId.equals(entry.getId())) {
                return entry;
            }
        }
        throw new BadRequestException("model not found");
    }
}
