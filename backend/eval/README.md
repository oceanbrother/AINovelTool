# Eval harness

Numbers turn "I built a RAG app" into "I engineer RAG like a working AI
engineer." These scripts hit the **running API** (`uvicorn app.main:app`) so they
measure the real system end to end, not mocked internals.

## Metrics covered

| Script | Metric | Pain / claim it backs |
| --- | --- | --- |
| `run_retrieval_eval.py` | Recall@k of relevant setting chunks; avg chunks; avg latency | Retrieval picks the *right* settings for a scene |
| `run_token_eval.py` | Token/char cost: full-context-dump vs RAG-selected | "Selective retrieval cuts per-call tokens by X%" |
| `run_idiom_hallucination_eval.py` | Fabrication rate of recommended 成语 (idioms not in the library) | Retrieval-grounded generation ≈ 0% fabrication vs raw LLM baseline |

## Usage

```bash
# 1. start the API and a seeded project
uvicorn app.main:app --reload

# 2. run an eval against a dataset
python eval/run_retrieval_eval.py --base-url http://localhost:8000 \
    --project-id 1 --dataset eval/datasets/retrieval_recall.example.json

python eval/run_idiom_hallucination_eval.py --base-url http://localhost:8000 \
    --dataset eval/datasets/idiom_hallucination.example.json
```

Datasets are plain JSON so they're easy to hand-label (~50 cases is enough to be
meaningful). Put your real labeled sets next to the `.example.json` files.
