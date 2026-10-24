# Databricks notebook source
# ruff: noqa: ERA001
"""Sync both Laws chunk tables to Lakebase as synced tables and index them for search."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Lakebase synced tables
# MAGIC
# MAGIC Copies `laws_chunks` and `laws_chunks_fixed` from Unity Catalog into Lakebase Postgres as read-only synced tables,
# MAGIC with `embedding` as a pgvector `vector(1024)`, then adds an HNSW cosine index and a GIN full-text index.
# MAGIC
# MAGIC The Laws are static and the chunk tables are overwritten on each ingest, so the sync uses `SNAPSHOT`: every
# MAGIC sync replaces the whole copy, and the source needs no Change Data Feed. Run `2_split_sections` first.

# COMMAND ----------

import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.runtime import dbutils
from databricks.sdk.service.pipelines import UpdateInfoState
from databricks.sdk.service.postgres import (
    NewPipelineSpec,
    SyncedTable,
    SyncedTableState,
    SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecPgSpecificType,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
    SyncedTableSyncedTableSpecTypeOverride,
)
from pyspark.sql import SparkSession

from referee_ai.config import load_config
from referee_ai.vector_search import LakebasePgVectorManager

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))
w = WorkspaceClient()
spark = SparkSession.builder.getOrCreate()
branch = f"projects/{cfg.lakebase_project_id}/branches/production"
SOURCES = {"laws_chunks": "laws_chunks_synced", "laws_chunks_fixed": "laws_chunks_fixed_synced"}

# COMMAND ----------

LakebasePgVectorManager(cfg, next(iter(SOURCES.values())), w).ensure_extension()

# COMMAND ----------

ONLINE = {SyncedTableState.SYNCED_TABLE_ONLINE, SyncedTableState.SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE}
FAILED = {SyncedTableState.SYNCED_TABLE_OFFLINE_FAILED, SyncedTableState.SYNCED_TABLE_ONLINE_PIPELINE_FAILED}


def sync(source: str, target: str) -> None:
    """Create the synced table, or start a new snapshot if it exists, and wait until it is up to date."""
    full_target = f"{cfg.full_schema_name}.{target}"
    name = f"synced_tables/{full_target}"
    update_id = None
    try:
        pipeline_id = w.postgres.get_synced_table(name=name).status.pipeline_id
        update_id = w.pipelines.start_update(pipeline_id=pipeline_id).update_id
        print(f"{target}: snapshot started, update {update_id}")
    except NotFound:
        w.postgres.create_synced_table(
            synced_table=SyncedTable(
                spec=SyncedTableSyncedTableSpec(
                    source_table_full_name=f"{cfg.full_schema_name}.{source}",
                    branch=branch,
                    postgres_database="databricks_postgres",
                    primary_key_columns=["id"],
                    scheduling_policy=SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.SNAPSHOT,
                    create_database_objects_if_missing=True,
                    new_pipeline_spec=NewPipelineSpec(
                        budget_policy_id=cfg.usage_policy_id, storage_catalog=cfg.catalog, storage_schema=cfg.schema
                    ),
                    type_overrides=[
                        SyncedTableSyncedTableSpecTypeOverride(
                            column_name="embedding",
                            pg_type=SyncedTableSyncedTableSpecPgSpecificType.PG_SPECIFIC_TYPE_VECTOR,
                            size=1024,
                        )
                    ],
                )
            ),
            synced_table_id=full_target,
        ).wait()
        print(f"{target}: created")

    while True:
        status = w.postgres.get_synced_table(name=name).status
        if update_id:
            update = w.pipelines.get_update(pipeline_id=status.pipeline_id, update_id=update_id).update
            if update.state == UpdateInfoState.COMPLETED:
                break
            if update.state in {UpdateInfoState.FAILED, UpdateInfoState.CANCELED}:
                raise RuntimeError(f"{target}: snapshot {update_id} ended in state {update.state}")
        elif status.detailed_state in ONLINE:
            break
        if status.detailed_state in FAILED:
            raise RuntimeError(f"{target}: {status.detailed_state} | {status.message}")
        print(f"{target}: waiting, {status.detailed_state}")
        time.sleep(30)
    print(f"{target}: up to date")


for source, target in SOURCES.items():
    sync(source, target)

# COMMAND ----------

summary = {}
for source, target in SOURCES.items():
    manager = LakebasePgVectorManager(cfg, target, w)
    manager.ensure_indexes()
    with manager.connection() as conn:
        postgres_rows = conn.execute(f"SELECT count(*) FROM {manager.table_name}").fetchone()[0]
        embedding_type = conn.execute(f"SELECT pg_typeof(embedding) FROM {manager.table_name} LIMIT 1").fetchone()[0]
        indexes = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = %s ORDER BY indexname",
            (cfg.schema, target),
        ).fetchall()
    summary[target] = {
        "postgres_rows": postgres_rows,
        "delta_rows": spark.table(f"{cfg.full_schema_name}.{source}").count(),
        "embedding_type": str(embedding_type),
        "indexes": [index[0] for index in indexes],
    }
    print(target, summary[target])

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "synced_tables": summary}))
