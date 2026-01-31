package com.bsl.search.execution;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SearchExecutionConfig {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService searchExecutor(@Value("${search.execution.pool-size:6}") int poolSize) {
        return Executors.newFixedThreadPool(Math.max(2, poolSize));
    }
}
