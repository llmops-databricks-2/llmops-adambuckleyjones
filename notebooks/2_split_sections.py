# Databricks notebook source
# ruff: noqa: ERA001
"""Split laws_parsed into laws (one row per section) and two embedded chunk tables, for comparing chunking."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Split the Laws into sections and chunks
# MAGIC
# MAGIC Reads the parsed Law files from `laws_parsed` and `page_map.csv` from the volume, then writes:
# MAGIC - `laws`: one row per numbered section;
# MAGIC - `laws_chunks`: one chunk per subheading block (the chosen strategy);
# MAGIC - `laws_chunks_fixed`: 500-character windows with 50 characters of overlap (the alternative, for comparison).
# MAGIC
# MAGIC Both chunk tables cite original Laws of the Game pages and carry an `id` (the synced-table primary key) and an
# MAGIC `embedding` from `embedding_endpoint`, computed with `ai_query`. Run `1_parse_laws` first.

# COMMAND ----------

import json

from databricks.sdk.runtime import dbutils
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, expr

from referee_ai.config import load_config
from referee_ai.laws_processor import Chunk, chunk_section, fixed_size_chunks, law_number_from_file, split_sections

dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")

cfg = load_config("project_config.yml", env=env)
volume = f"/Volumes/{cfg.catalog}/{cfg.schema}/{cfg.volume}"
laws_table = f"{cfg.full_schema_name}.laws"
chunks_table = f"{cfg.full_schema_name}.laws_chunks"
fixed_table = f"{cfg.full_schema_name}.laws_chunks_fixed"

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
fixed_chunks = [chunk for section in sections for chunk in fixed_size_chunks(section)]
print(f"{len(sections)} sections, {len(chunks)} chunks, {len(fixed_chunks)} fixed-size chunks")

# COMMAND ----------

laws_df = spark.createDataFrame(
    [(s.law_number, s.law_title, s.section, s.section_title, s.text, s.pages) for s in sections],
    "law_number INT, law_title STRING, section STRING, section_title STRING, text STRING, pages ARRAY<INT>",
)


def embedded_chunks(chunk_list: list[Chunk]) -> DataFrame:
    """Chunks as a DataFrame with an id and an embedding of the full chunk text, heading included."""
    df = spark.createDataFrame(
        [
            (c.chunk_id, c.law_number, c.law_title, c.section, c.section_title, c.subheading, c.text, c.pages)
            for c in chunk_list
        ],
        "chunk_id STRING, law_number INT, law_title STRING, section STRING, section_title STRING, "
        "subheading STRING, text STRING, pages ARRAY<INT>",
    )
    endpoint = cfg.embedding_endpoint.replace("'", "''")
    return df.withColumn("id", col("chunk_id")).withColumn(
        "embedding", expr(f"CAST(ai_query('{endpoint}', text) AS ARRAY<FLOAT>)")
    )


laws_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(laws_table)
for table, chunk_list in ((chunks_table, chunks), (fixed_table, fixed_chunks)):
    embedded_chunks(chunk_list).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)

# COMMAND ----------

for table in (laws_table, chunks_table, fixed_table):
    df = spark.table(table)
    print(f"{table}: {df.count()} rows")
    df.printSchema()
    df.drop("embedding").orderBy("law_number", "section").show(5, truncate=80)

# COMMAND ----------

dbutils.notebook.exit(
    json.dumps(
        {"status": "ok", "laws": len(sections), "laws_chunks": len(chunks), "laws_chunks_fixed": len(fixed_chunks)}
    )
)
