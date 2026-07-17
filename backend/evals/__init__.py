"""On-demand quality eval harness — recall@k/nDCG@k against real embeddings,
grounding-guard catch rate against synthetic hallucinations.

Not part of the regular pytest/CI run (CLAUDE.md, "Тестирование промптов":
eval-наборы run by request/nightly, not in every CI pass) — see
run_retrieval_eval.py and run_hallucination_eval.py for usage.
"""
