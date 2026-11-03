# Databricks notebook source
# ruff: noqa: ERA001
"""Ask the Referee AI Laws Genie space structured questions and match situations, and record its answers and SQL."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Genie space: structured questions and match situations
# MAGIC
# MAGIC Asks the space deployed by `resources/genie_space.yml` four structured questions, which it should answer with
# MAGIC SQL, and five match situations, which it should decline: the Laws text is hidden from it, so situations go to
# MAGIC `search_laws`. Each question starts its own conversation. The exit value holds every answer with its SQL and
# MAGIC latency.

# COMMAND ----------

import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils
from loguru import logger

dbutils.widgets.text("genie_space_id", "")
space_id = dbutils.widgets.get("genie_space_id")
workspace = WorkspaceClient()

QUESTIONS = [
    ("structured", "List the sections of Law 12"),
    ("structured", "Which sections are on page 119?"),
    ("structured", "How many sections does each Law have, and on which page does it start?"),
    ("structured", "What are the subheadings of section 12.4?"),
    ("situation", "A defender deliberately handles the ball on the goal line to stop a goal. What is the decision?"),
    ("situation", "The keeper picks the ball up after his own teammate kicked it back to him. What happens?"),
    (
        "situation",
        "An attacker standing behind the last defender receives the ball straight from a throw-in. Is he offside?",
    ),
    ("situation", "How far back does the wall have to stand at a free kick?"),
    ("situation", "The goalkeeper holds onto the ball for too long. What is the restart?"),
]

# COMMAND ----------

results = []
for kind, question in QUESTIONS:
    start = time.perf_counter()
    message = workspace.genie.start_conversation_and_wait(space_id=space_id, content=question)
    attachments = message.attachments or []
    results.append(
        {
            "kind": kind,
            "question": question,
            "status": message.status.value,
            "answer": "\n".join(a.text.content for a in attachments if a.text and a.text.content),
            "sql": [a.query.query for a in attachments if a.query and a.query.query],
            "latency_s": round(time.perf_counter() - start, 1),
        }
    )
    logger.info(f"[{kind}] {question}\nSQL: {results[-1]['sql']}\nA: {results[-1]['answer']}\n")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "space_id": space_id, "results": results}))
