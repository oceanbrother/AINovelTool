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

## Measured results (2026-07, Windows / CPU bge-m3 / deepseek-chat)

| Metric | Result |
| --- | --- |
| Recall@6, 30-case labeled set ([retrieval_recall.v1.json](datasets/retrieval_recall.v1.json)) | **1.000**, mean latency 256ms |
| Context compression vs full-dump baseline | **62.5%** (fixed top-k=6; grows with library size) |
| Idiom fabrication rate, 20 scenes ([idiom_scenes.v1.json](datasets/idiom_scenes.v1.json)) | **0.0%** grounded (61 suggestions) vs **20.0%** raw-LLM baseline (100 suggestions) |
| Perf: retrieval P95 / SSE TTFT P50 / stream rate | 161ms / 3.1s / 61 events/s |

Fabrication = suggested idiom absent from the authority set (chinese-xinhua's
~31k dictionary ∪ the curated library). The grounded pipeline can only emit
recalled library rows, so its rate is structurally 0 — the eval verifies that
independently. Baseline "fabrications" include both outright inventions
(数据如海、荧屏孤照) and unverifiable modern phrases — either way, nothing the
tool can vouch for.

## Usage

```bash
# 1. start the API; seed a project + libraries
uvicorn app.main:app --reload
python eval/seed_eval_settings.py --project-id <id>
python scripts/import_idioms.py --source <path>/idiom.json   # chinese-xinhua, MIT

# 2. run evals
python eval/run_retrieval_eval.py --project-id <id> \
    --dataset eval/datasets/retrieval_recall.v1.json
python eval/run_token_eval.py --project-id <id> \
    --dataset eval/datasets/retrieval_recall.v1.json
python eval/run_perf_eval.py --project-id <id> [--skip-llm]
python eval/run_idiom_hallucination_eval.py \
    --dataset eval/datasets/idiom_scenes.v1.json --truth <path>/idiom.json
```

Datasets are plain JSON so they're easy to hand-label. `.example.json` files
show the shape; the `.v1.json` files are the real labeled sets behind the
numbers above.
