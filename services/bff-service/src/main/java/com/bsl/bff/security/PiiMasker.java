package com.bsl.bff.security;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class PiiMasker {
    private final PiiMaskingProperties properties;
    private final ObjectMapper objectMapper;

    public PiiMasker(PiiMaskingProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public String maskJson(String json) {
        if (json == null || json.isBlank() || properties == null || !properties.isEnabled()) {
            return json;
        }
        try {
            JsonNode root = objectMapper.readTree(json);
            JsonNode masked = maskNode(root);
            return objectMapper.writeValueAsString(masked);
        } catch (JsonProcessingException ex) {
            return json;
        }
    }

    private JsonNode maskNode(JsonNode node) {
        if (node == null) {
            return null;
        }
        if (node.isObject()) {
            ObjectNode obj = (ObjectNode) node.deepCopy();
            Set<String> keysToMask = resolveKeys();
            obj.fieldNames().forEachRemaining(field -> {
                JsonNode value = obj.get(field);
                if (keysToMask.contains(field.toLowerCase(Locale.ROOT))) {
                    obj.put(field, properties.getMask());
                } else {
                    obj.set(field, maskNode(value));
                }
            });
            return obj;
        }
        if (node.isArray()) {
            ArrayNode array = (ArrayNode) node.deepCopy();
            for (int i = 0; i < array.size(); i++) {
                array.set(i, maskNode(array.get(i)));
            }
            return array;
        }
        return node;
    }

    private Set<String> resolveKeys() {
        Set<String> keys = new HashSet<>();
        if (properties.getKeys() != null && !properties.getKeys().isEmpty()) {
            for (String key : properties.getKeys()) {
                if (key != null && !key.isBlank()) {
                    keys.add(key.toLowerCase(Locale.ROOT));
                }
            }
        }
        if (keys.isEmpty()) {
            keys.add("name");
            keys.add("email");
            keys.add("phone");
            keys.add("addr1");
            keys.add("addr2");
            keys.add("zip");
            keys.add("address");
            keys.add("card_number");
            keys.add("cardnumber");
        }
        return keys;
    }
}
