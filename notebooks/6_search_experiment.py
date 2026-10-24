# Databricks notebook source
# ruff: noqa: ERA001
"""Compare semantic, filtered and hybrid search over both chunking strategies on referee questions."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Search experiment
# MAGIC
# MAGIC Five referee questions with a known answer section, each searched three ways on both synced tables:
# MAGIC - **semantic**: cosine similarity on the embedding;
# MAGIC - **filtered**: semantic, only within the Law the answer is in;
# MAGIC - **hybrid**: 0.7 x cosine similarity + 0.3 x PostgreSQL full-text rank.
# MAGIC
# MAGIC A search is a hit when the expected section is in the top 3. The exit value holds every top 3. Run
# MAGIC `5_synced_tables` first.

# COMMAND ----------

import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils

from referee_ai.config import load_config
from referee_ai.vector_search import LakebasePgVectorManager

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))
w = WorkspaceClient()

TABLES = {"section": "laws_chunks_synced", "fixed": "laws_chunks_fixed_synced"}
QUESTIONS = [
    ("A defender deliberately handles the ball on the goal line to stop a goal. What is the sanction?", 12, "12.4"),
    ("DOGSO", 12, "12.4"),
    ("What happens if the goalkeeper holds the ball in their hands for too long?", 12, "12.3"),
    ("Can a player be penalised for offside when receiving the ball from a throw-in?", 11, "11.3"),
    ("How far must opponents be from the ball at a free kick?", 13, "13.2"),
]
TOP = 3

# COMMAND ----------

results = []
for chunking, table in TABLES.items():
    manager = LakebasePgVectorManager(cfg, table, w)
    for question, law, expected in QUESTIONS:
        runs = {
            "semantic": manager.search(question, TOP),
            "filtered": manager.search(question, TOP, law_number=law),
            "hybrid": manager.hybrid_search(question, TOP),
        }
        for method, rows in runs.items():
            sections = [row["section"] for row in rows]
            results.append(
                {
                    "chunking": chunking,
                    "method": method,
                    "question": question,
                    "expected": expected,
                    "hit": expected in sections,
                    "rank": sections.index(expected) + 1 if expected in sections else None,
                    "top": [
                        {
                            "id": row["id"],
                            "section": row["section"],
                            "pages": row["pages"],
                            "score": round(float(row["score"]), 4),
                            **({"text_score": round(float(row["text_score"]), 4)} if "text_score" in row else {}),
                        }
                        for row in rows
                    ],
                }
            )
            print(f"{chunking:7} {method:8} {'HIT ' if results[-1]['hit'] else 'miss'} {question[:60]} -> {sections}")

# COMMAND ----------

hit_rates = {}
for chunking in TABLES:
    for method in ("semantic", "filtered", "hybrid"):
        hits = [r["hit"] for r in results if r["chunking"] == chunking and r["method"] == method]
        hit_rates[f"{chunking}/{method}"] = f"{sum(hits)}/{len(hits)}"
print(hit_rates)

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "hit_rates": hit_rates, "results": results}, default=str))
