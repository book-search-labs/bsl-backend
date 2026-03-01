package com.bsl.search.embed;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.springframework.stereotype.Component;

@Component
public class ToyEmbedder {
    public static final int DIMENSION = 384;

    public List<Double> embed(String text) {
        long seed = stableSeed(text);
        Random random = new Random(seed);
        double[] values = new double[DIMENSION];
        double sumSquares = 0.0;
        for (int i = 0; i < DIMENSION; i++) {
            double value = random.nextDouble();
            values[i] = value;
            sumSquares += value * value;
        }
        double norm = Math.sqrt(sumSquares);
        if (norm == 0.0) {
            norm = 1.0;
        }
        List<Double> vector = new ArrayList<>(DIMENSION);
        for (double value : values) {
            vector.add(value / norm);
        }
        return vector;
    }

    private long stableSeed(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            ByteBuffer buffer = ByteBuffer.wrap(hash, 0, 8);
            return buffer.getLong();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
