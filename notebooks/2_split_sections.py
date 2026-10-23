# Databricks notebook source
# ruff: noqa: ERA001
"""Split laws_parsed into the laws (one row per section) and laws_chunks (retrieval chunks) tables."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Split the Laws into sections and chunks
# MAGIC
# MAGIC Stage 2 of `plan.md`. Reads the parsed Law files from `laws_parsed` and `page_map.csv` from the volume, then
# MAGIC writes `laws` and `laws_chunks`, both citing original Laws of the Game pages. Run `1_parse_laws` first.

# COMMAND ----------

import json

from databricks.sdk.runtime import dbutils
from pyspark.sql import SparkSession

from referee_ai.config import load_config
from referee_ai.laws_processor import chunk_section, law_number_from_file, split_sections

dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")

cfg = load_config("project_config.yml", env=env)
volume = f"/Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}"
laws_table = f"{cfg.full_schema_name}.laws"
chunks_table = f"{cfg.full_schema_name}.laws_chunks"

spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

page_map = {
    (row["file"], int(row["file_page"])): int(row["original_page"])
    for row in spark.read.csv(f"{volume}/page_map.csv", header=True).collect()
}
parsed = spark.table(f"{cfg.full_schema_name}.laws_parsed").selectExpr("path", "to_json(parsed) AS doc").collect()

sections = []
for row in parsed:
    file_name = row["path"].split("/")[-1]
    if law_number_from_file(file_name) is not None:
        sections.extend(split_sections(file_name, json.loads(row["doc"])["document"]["elements"], page_map))
chunks = [chunk for section in sections for chunk in chunk_section(section)]
print(f"{len(sections)} sections, {len(chunks)} chunks")

# COMMAND ----------

laws_df = spark.createDataFrame(
    [(s.law_number, s.law_title, s.section, s.section_title, s.text, s.pages) for s in sections],
    "law_number INT, law_title STRING, section STRING, section_title STRING, text STRING, pages ARRAY<INT>",
)
chunks_df = spark.createDataFrame(
    [
        (c.chunk_id, c.law_number, c.law_title, c.section, c.section_title, c.subheading, c.text, c.pages)
        for c in chunks
    ],
    "chunk_id STRING, law_number INT, law_title STRING, section STRING, section_title STRING, subheading STRING, "
    "text STRING, pages ARRAY<INT>",
)

laws_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(laws_table)
chunks_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(chunks_table)

dbutils.notebook.exit(json.dumps({"status": "ok", "laws": len(sections), "laws_chunks": len(chunks)}))
