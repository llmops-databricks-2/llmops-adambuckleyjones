# Databricks notebook source
# ruff: noqa: ERA001
"""Save a conversation to Lakebase as the dev service principal, read it back, and check sessions stay separate."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Session memory in Lakebase
# MAGIC
# MAGIC Connects as `sp-deploy-adambuckleyjones-dev`, with the client ID and secret the course stored as Unity Catalog
# MAGIC secrets in the project schema. Saves a question and answer under one session, reads them back from a new
# MAGIC `LakebaseMemory` (so they come from the database, not the object), and checks a second session is empty. Fails
# MAGIC if any check fails.

# COMMAND ----------

import json
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils
from loguru import logger

from referee_ai.config import load_config
from referee_ai.memory import LakebaseMemory

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))

spn = WorkspaceClient(
    host=WorkspaceClient().config.host,
    client_id=dbutils.secrets.get(catalog=cfg.catalog, schema=cfg.schema, key="databricks_client_id"),
    client_secret=dbutils.secrets.get(catalog=cfg.catalog, schema=cfg.schema, key="databricks_client_secret"),
)
identity = spn.current_user.me()
logger.info(f"Connecting to Lakebase as {identity.display_name} ({identity.user_name})")

# COMMAND ----------

LakebaseMemory(cfg, workspace=spn).ensure_schema()

session_a, session_b = str(uuid4()), str(uuid4())
turn = [
    {"role": "user", "content": "A defender handles the ball on the goal line to stop a goal. What is the decision?"},
    {"role": "assistant", "content": "Penalty kick and sending-off for denying an obvious goal (12.3, p119)."},
]
LakebaseMemory(cfg, workspace=spn).save_messages(session_a, turn)

loaded_a = LakebaseMemory(cfg, workspace=spn).load_messages(session_a)
loaded_b = LakebaseMemory(cfg, workspace=spn).load_messages(session_b)
logger.info(f"Session A: {loaded_a}\nSession B: {loaded_b}")

assert loaded_a == turn, "session A didn't come back as saved"
assert loaded_b == [], "session B should be empty"

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {
            "status": "ok",
            "connected_as": {"display_name": identity.display_name, "user_name": identity.user_name},
            "session_a": {"id": session_a, "messages": loaded_a},
            "session_b": {"id": session_b, "messages": loaded_b},
        }
    )
)
