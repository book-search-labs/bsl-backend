package com.bsl.bff.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class KdcCategoryResponse {
    private String version;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("request_id")
    private String requestId;

    private List<KdcCategoryNode> categories;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getTraceId() {
        return traceId;
    }

    public void setTraceId(String traceId) {
        this.traceId = traceId;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public List<KdcCategoryNode> getCategories() {
        return categories;
    }

    public void setCategories(List<KdcCategoryNode> categories) {
        this.categories = categories;
    }

    public static class KdcCategoryNode {
        private Long id;
        private String code;
        private String name;
        private Integer depth;
        private List<KdcCategoryNode> children;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public String getCode() {
            return code;
        }

        public void setCode(String code) {
            this.code = code;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getDepth() {
            return depth;
        }

        public void setDepth(Integer depth) {
            this.depth = depth;
        }

        public List<KdcCategoryNode> getChildren() {
            return children;
        }

        public void setChildren(List<KdcCategoryNode> children) {
            this.children = children;
        }
    }
}
