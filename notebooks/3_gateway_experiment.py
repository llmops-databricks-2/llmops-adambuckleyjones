# Databricks notebook source
# ruff: noqa: ERA001
"""Ask the course chat model referee questions through the AI Gateway, with no retrieval, and record the results."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Chat model through the AI Gateway
# MAGIC
# MAGIC Calls `llm_endpoint` from `project_config.yml` (`course_ops.gateway.chat`, GPT-OSS-120B) with the OpenAI client
# MAGIC pointed at the workspace AI Gateway. `WorkspaceClient` authenticates; its token goes only into the request
# MAGIC header and is never printed. No Laws text is given to the model, so the answers show what it knows on its own.
# MAGIC The exit value holds every answer with its token usage and latency.

# COMMAND ----------

import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils
from openai import OpenAI

from referee_ai.config import load_config

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))

workspace = WorkspaceClient()
client = OpenAI(
    base_url=f"{workspace.config.host}/ai-gateway/mlflow/v1",
    api_key=workspace.config.authenticate()["Authorization"].removeprefix("Bearer "),
)

SYSTEM_PROMPT = "You help football referees. Answer questions on the IFAB Laws of the Game briefly and cite the Law."
PROMPTS = [
    "What is the minimum distance opponents must be from the ball at a free kick?",
    "A defender deliberately handles the ball on the goal line to stop a certain goal. What is the decision?",
    "Can a player be penalised for offside if they receive the ball directly from a throw-in?",
    "Under the 2026/27 Laws, what happens if a goalkeeper holds the ball in their hands for too long?",
    "On which page of the IFAB Laws of the Game 2026/27 is the offside offence defined?",
]

# COMMAND ----------

results = []
for prompt in PROMPTS:
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=cfg.llm_endpoint,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        reasoning_effort="low",
        max_tokens=1024,
    )
    results.append(
        {
            "prompt": prompt,
            "answer": response.choices[0].message.content,
            "finish_reason": response.choices[0].finish_reason,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "latency_s": round(time.perf_counter() - start, 2),
        }
    )
    print(f"Q: {prompt}\nA: {results[-1]['answer']}\n{results[-1]['total_tokens']} tokens\n")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "model": response.model, "results": results}))
