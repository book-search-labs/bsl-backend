package com.bsl.search.retrieval;

public interface Retriever {
    String name();

    RetrievalStageResult retrieve(RetrievalStageContext context);
}
