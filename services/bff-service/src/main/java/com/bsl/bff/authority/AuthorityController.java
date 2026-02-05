package com.bsl.bff.authority;

import com.bsl.bff.authority.dto.AgentAliasDto;
import com.bsl.bff.authority.dto.AgentAliasResponse;
import com.bsl.bff.authority.dto.AgentAliasUpsertRequest;
import com.bsl.bff.authority.dto.AuthorityListResponse;
import com.bsl.bff.authority.dto.AuthorityMergeGroupDto;
import com.bsl.bff.authority.dto.AuthorityMergeGroupResolveRequest;
import com.bsl.bff.authority.dto.AuthorityMergeGroupResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.DownstreamException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import java.util.List;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/admin/authority")
public class AuthorityController {
    private static final int DEFAULT_LIMIT = 50;
    private static final int MAX_LIMIT = 500;

    private final AuthorityRepository repository;

    public AuthorityController(AuthorityRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/merge-groups")
    public AuthorityListResponse<AuthorityMergeGroupDto> listMergeGroups(
        @RequestParam(value = "limit", required = false) Integer limit,
        @RequestParam(value = "status", required = false) String status
    ) {
        int resolvedLimit = clampLimit(limit);
        List<AuthorityMergeGroupDto> items = repository.listMergeGroups(resolvedLimit, status);
        return buildListResponse(items);
    }

    @PostMapping("/merge-groups/{id}/resolve")
    public AuthorityMergeGroupResponse resolveMergeGroup(
        @PathVariable("id") long groupId,
        @RequestBody(required = false) AuthorityMergeGroupResolveRequest request
    ) {
        if (request == null || request.getMasterMaterialId() == null || request.getMasterMaterialId().isBlank()) {
            throw new BadRequestException("master_material_id is required");
        }
        Optional<AuthorityMergeGroupDto> updated = repository.resolveMergeGroup(
            groupId,
            request.getMasterMaterialId(),
            request.getStatus()
        );
        if (updated.isEmpty()) {
            throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "merge_group not found");
        }
        return buildMergeResponse(updated.get());
    }

    @GetMapping("/agent-aliases")
    public AuthorityListResponse<AgentAliasDto> listAgentAliases(
        @RequestParam(value = "limit", required = false) Integer limit,
        @RequestParam(value = "q", required = false) String query,
        @RequestParam(value = "status", required = false) String status
    ) {
        int resolvedLimit = clampLimit(limit);
        List<AgentAliasDto> items = repository.listAgentAliases(resolvedLimit, query, status);
        return buildListResponse(items);
    }

    @PostMapping("/agent-aliases")
    public AgentAliasResponse upsertAlias(@RequestBody(required = false) AgentAliasUpsertRequest request) {
        if (request == null || request.getAliasName() == null || request.getAliasName().isBlank()) {
            throw new BadRequestException("alias_name is required");
        }
        if (request.getCanonicalName() == null || request.getCanonicalName().isBlank()) {
            throw new BadRequestException("canonical_name is required");
        }
        Optional<AgentAliasDto> updated = repository.upsertAgentAlias(
            request.getAliasName(),
            request.getCanonicalName(),
            request.getCanonicalAgentId(),
            request.getStatus()
        );
        if (updated.isEmpty()) {
            throw new DownstreamException(HttpStatus.BAD_GATEWAY, "alias_update_failed", "Alias update failed");
        }
        return buildAliasResponse(updated.get());
    }

    @DeleteMapping("/agent-aliases/{id}")
    public AgentAliasResponse deleteAlias(@PathVariable("id") long aliasId) {
        Optional<AgentAliasDto> updated = repository.deleteAgentAlias(aliasId);
        if (updated.isEmpty()) {
            throw new DownstreamException(HttpStatus.NOT_FOUND, "not_found", "alias not found");
        }
        return buildAliasResponse(updated.get());
    }

    private int clampLimit(Integer limit) {
        int value = limit == null ? DEFAULT_LIMIT : limit;
        if (value < 1) {
            value = DEFAULT_LIMIT;
        }
        return Math.min(value, MAX_LIMIT);
    }

    private <T> AuthorityListResponse<T> buildListResponse(List<T> items) {
        RequestContext context = RequestContextHolder.get();
        AuthorityListResponse<T> response = new AuthorityListResponse<>();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setItems(items);
        response.setCount(items == null ? 0 : items.size());
        return response;
    }

    private AuthorityMergeGroupResponse buildMergeResponse(AuthorityMergeGroupDto group) {
        RequestContext context = RequestContextHolder.get();
        AuthorityMergeGroupResponse response = new AuthorityMergeGroupResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setGroup(group);
        return response;
    }

    private AgentAliasResponse buildAliasResponse(AgentAliasDto alias) {
        RequestContext context = RequestContextHolder.get();
        AgentAliasResponse response = new AgentAliasResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setAlias(alias);
        return response;
    }
}
