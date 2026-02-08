.PHONY: all eval-embedding eval-rerank local-llm-up local-llm-down local-llm-health local-up up down

LOCAL_LLM_MODEL ?= llama3.1:8b-instruct
LOCAL_LLM_COMPOSE ?= compose.yaml
LOCAL_LLM_PROFILE ?= llm
LOCAL_LLM_PROJECT ?= bsl-llm

all:
	@echo "Available targets: eval-embedding, eval-rerank, up, down, local-llm-up, local-llm-down, local-llm-health"

eval-embedding:
	python3 scripts/eval/embedding_eval.py

eval-rerank:
	python3 scripts/eval/rerank_eval.py

local-up:
	./scripts/local_up.sh

local-llm-up:
	@docker compose -p $(LOCAL_LLM_PROJECT) -f $(LOCAL_LLM_COMPOSE) --profile $(LOCAL_LLM_PROFILE) up -d ollama
	@for i in $$(seq 1 30); do \
		if docker exec ollama ollama list >/dev/null 2>&1; then break; fi; \
		sleep 1; \
	done
	@docker exec ollama ollama list | grep -q "$(LOCAL_LLM_MODEL)" || docker exec ollama ollama pull "$(LOCAL_LLM_MODEL)"

local-llm-down:
	@docker compose -p $(LOCAL_LLM_PROJECT) -f $(LOCAL_LLM_COMPOSE) --profile $(LOCAL_LLM_PROFILE) down

local-llm-health:
	@curl -fsS http://localhost:11434/v1/models

up: local-up local-llm-up

down: local-llm-down
	./scripts/local_down.sh
