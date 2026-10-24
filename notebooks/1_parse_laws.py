# Databricks notebook source
# ruff: noqa: ERA001
"""Parse the Laws of the Game PDFs in the laws_files volume into the laws_parsed table."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Parse the Laws of the Game
# MAGIC
# MAGIC Stage 1 of `plan.md`. Reads every PDF under `<volume>/raw/` and writes one row per file to `laws_parsed`,
# MAGIC with the `ai_parse_document` output as a VARIANT. Upload the PDF to the volume first.

# COMMAND ----------

from databricks.sdk.runtime import dbutils
from pyspark.sql import SparkSession

from referee_ai.config import load_config

dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")

cfg = load_config("project_config.yml", env=env)
raw_dir = f"/Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}/raw/"
parsed_table = f"{cfg.full_schema_name}.laws_parsed"

spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE TABLE {parsed_table} AS
    SELECT path, ai_parse_document(content) AS parsed, current_timestamp() AS parsed_at
    FROM READ_FILES('{raw_dir}', format => 'binaryFile')
""")
print(f"Parsed {raw_dir} into {parsed_table}")

# COMMAND ----------

spark.sql(f"""
    SELECT path,
           size(cast(parsed:document:pages AS ARRAY<VARIANT>)) AS pages,
           size(cast(parsed:document:elements AS ARRAY<VARIANT>)) AS elements,
           parsed:error_status AS error_status
    FROM {parsed_table}
""").show(truncate=False)
