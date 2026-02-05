package com.bsl.commerce.common;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

public final class JsonUtils {
    private JsonUtils() {
    }

    public static String toJson(ObjectMapper mapper, Object value) {
        if (value == null) {
            return null;
        }
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            return null;
        }
    }

    public static String mapToJson(ObjectMapper mapper, Map<String, Object> value) {
        return toJson(mapper, value);
    }
}
