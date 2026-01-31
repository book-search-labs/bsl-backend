package com.bsl.bff.models;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.client.MisServiceClient;
import com.bsl.bff.client.dto.MisModelsResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.ops.dto.OpsListResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/models")
public class ModelOpsController {
    private static final int DEFAULT_LIMIT = 10;
    private static final int MAX_LIMIT = 50;

    private final MisServiceClient misServiceClient;
    private final ModelRegistryStore registryStore;
    private final EvalRunStore evalRunStore;

    public ModelOpsController(
        MisServiceClient misServiceClient,
        ModelRegistryStore registryStore,
        EvalRunStore evalRunStore
    ) {
        this.misServiceClient = misServiceClient;
        this.registryStore = registryStore;
        this.evalRunStore = evalRunStore;
    }

    @GetMapping("/registry")
    public MisModelsResponse registry() {
        RequestContext context = RequestContextHolder.get();
        try {
            MisModelsResponse response = misServiceClient.listModels(context);
            if (response != null) {
                return response;
            }
        } catch (DownstreamException ex) {
            // fallback to local registry file
        }
        return registryStore.loadAsResponse(context);
    }

    @PostMapping("/registry/activate")
    public BffAckResponse activate(@RequestBody(required = false) ModelRegistryActionRequest request) {
        if (request == null || request.getModelId() == null || request.getModelId().isBlank()) {
            throw new BadRequestException("model_id is required");
        }
        registryStore.activate(request.getModelId(), request.getTask());
        return ack("ok");
    }

    @PostMapping("/registry/rollback")
    public BffAckResponse rollback(@RequestBody(required = false) ModelRegistryActionRequest request) {
        if (request == null || request.getModelId() == null || request.getModelId().isBlank()) {
            throw new BadRequestException("model_id is required");
        }
        registryStore.activate(request.getModelId(), request.getTask());
        return ack("ok");
    }

    @PostMapping("/registry/canary")
    public BffAckResponse canary(@RequestBody(required = false) ModelRegistryActionRequest request) {
        if (request == null || request.getModelId() == null || request.getModelId().isBlank()) {
            throw new BadRequestException("model_id is required");
        }
        double weight = request.getCanaryWeight() == null ? 0.0 : request.getCanaryWeight();
        registryStore.setCanary(request.getModelId(), request.getTask(), weight);
        return ack("ok");
    }

    @GetMapping("/eval-runs")
    public OpsListResponse<EvalRunReport> listEvalRuns(
        @RequestParam(value = "limit", required = false) Integer limit
    ) {
        int resolvedLimit = clampLimit(limit);
        List<EvalRunReport> items = evalRunStore.listRuns(resolvedLimit);
        OpsListResponse<EvalRunReport> response = new OpsListResponse<>();
        RequestContext context = RequestContextHolder.get();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setItems(items);
        response.setCount(items == null ? 0 : items.size());
        return response;
    }

    private int clampLimit(Integer limit) {
        int value = limit == null ? DEFAULT_LIMIT : limit;
        if (value < 1) {
            value = DEFAULT_LIMIT;
        }
        return Math.min(value, MAX_LIMIT);
    }

    private BffAckResponse ack(String status) {
        RequestContext context = RequestContextHolder.get();
        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus(status);
        return response;
    }
}
