package com.bsl.bff.ops;

import com.bsl.bff.api.dto.BffAckResponse;
import com.bsl.bff.common.BadRequestException;
import com.bsl.bff.common.RequestContext;
import com.bsl.bff.common.RequestContextHolder;
import com.bsl.bff.ops.dto.RagEvalLabelRequest;
import com.bsl.bff.ops.dto.RagIndexRequest;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/admin/rag")
public class RagOpsController {
    private final OpsRepository opsRepository;

    public RagOpsController(OpsRepository opsRepository) {
        this.opsRepository = opsRepository;
    }

    @PostMapping(path = "/docs/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public BffAckResponse uploadDoc(
        @RequestPart("file") MultipartFile file,
        @RequestParam(value = "source", required = false) String source
    ) {
        if (file == null || file.isEmpty()) {
            throw new BadRequestException("file is required");
        }
        String originalName = file.getOriginalFilename() == null ? "upload" : file.getOriginalFilename();
        String safeName = originalName.replaceAll("[^a-zA-Z0-9._-]", "_");
        Path targetDir = Path.of("data", "rag", "uploads");
        Path target = targetDir.resolve(Instant.now().toEpochMilli() + "_" + safeName);
        try {
            Files.createDirectories(targetDir);
            file.transferTo(target);
        } catch (IOException ex) {
            throw new BadRequestException("failed to store file");
        }
        Map<String, Object> payload = new HashMap<>();
        payload.put("file_name", target.getFileName().toString());
        payload.put("source", source);
        payload.put("size", file.getSize());
        opsRepository.createOpsTask("RAG_DOC_UPLOAD", payload);
        return ack();
    }

    @PostMapping(path = "/index/reindex", consumes = MediaType.APPLICATION_JSON_VALUE)
    public BffAckResponse reindex(@RequestBody(required = false) RagIndexRequest request) {
        Map<String, Object> payload = new HashMap<>();
        if (request != null) {
            payload.put("source_dir", request.getSourceDir());
            payload.put("docs_index", request.getDocsIndex());
            payload.put("vec_index", request.getVecIndex());
            payload.put("note", request.getNote());
        }
        opsRepository.createOpsTask("RAG_REINDEX", payload);
        return ack();
    }

    @PostMapping(path = "/index/rollback", consumes = MediaType.APPLICATION_JSON_VALUE)
    public BffAckResponse rollback(@RequestBody(required = false) RagIndexRequest request) {
        Map<String, Object> payload = new HashMap<>();
        if (request != null) {
            payload.put("docs_index", request.getDocsIndex());
            payload.put("vec_index", request.getVecIndex());
            payload.put("note", request.getNote());
        }
        opsRepository.createOpsTask("RAG_ROLLBACK", payload);
        return ack();
    }

    @PostMapping(path = "/eval/label", consumes = MediaType.APPLICATION_JSON_VALUE)
    public BffAckResponse label(@RequestBody(required = false) RagEvalLabelRequest request) {
        if (request == null || request.getQuestion() == null || request.getQuestion().isBlank()) {
            throw new BadRequestException("question is required");
        }
        Map<String, Object> payload = new HashMap<>();
        payload.put("question_id", request.getQuestionId());
        payload.put("question", request.getQuestion());
        payload.put("answer", request.getAnswer());
        payload.put("evidence", request.getEvidence());
        payload.put("rating", request.getRating());
        payload.put("comment", request.getComment());
        opsRepository.createOpsTask("RAG_EVAL_LABEL", payload);
        return ack();
    }

    private BffAckResponse ack() {
        RequestContext context = RequestContextHolder.get();
        BffAckResponse response = new BffAckResponse();
        response.setVersion("v1");
        response.setTraceId(context == null ? null : context.getTraceId());
        response.setRequestId(context == null ? null : context.getRequestId());
        response.setStatus("ok");
        return response;
    }
}
