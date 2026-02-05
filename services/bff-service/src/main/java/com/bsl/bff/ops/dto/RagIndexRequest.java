package com.bsl.bff.ops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class RagIndexRequest {
    @JsonProperty("source_dir")
    private String sourceDir;
    @JsonProperty("docs_index")
    private String docsIndex;
    @JsonProperty("vec_index")
    private String vecIndex;
    private String note;

    public String getSourceDir() {
        return sourceDir;
    }

    public void setSourceDir(String sourceDir) {
        this.sourceDir = sourceDir;
    }

    public String getDocsIndex() {
        return docsIndex;
    }

    public void setDocsIndex(String docsIndex) {
        this.docsIndex = docsIndex;
    }

    public String getVecIndex() {
        return vecIndex;
    }

    public void setVecIndex(String vecIndex) {
        this.vecIndex = vecIndex;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
