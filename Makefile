.PHONY: all eval-embedding eval-rerank

all:
	@echo "Available targets: eval-embedding, eval-rerank"

eval-embedding:
	python3 scripts/eval/embedding_eval.py

eval-rerank:
	python3 scripts/eval/rerank_eval.py
