# Databricks notebook source
# ruff: noqa: ERA001
"""Inspect the parsed documents and chunk tables, and compare chunk sizes for the two chunking strategies."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Review the documents and chunks
# MAGIC
# MAGIC Inspects `laws_parsed`, `laws`, `laws_chunks` (one chunk per subheading block) and `laws_chunks_fixed`
# MAGIC (500-character windows, 50 overlap): row counts, schemas, samples, and chunk sizes in characters, words and
# MAGIC estimated tokens (about 4 characters per token). The exit value holds the size statistics.

# COMMAND ----------

import json

from databricks.sdk.runtime import dbutils
from pyspark.sql import SparkSession

from referee_ai.config import load_config

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))
schema = cfg.full_schema_name
spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parsed documents

# COMMAND ----------

spark.sql(f"""
    SELECT element_at(split(path, '/'), -1) AS file,
           size(cast(parsed:document:pages AS ARRAY<VARIANT>)) AS pages,
           size(cast(parsed:document:elements AS ARRAY<VARIANT>)) AS elements,
           parsed:error_status::string AS error_status
    FROM {schema}.laws_parsed ORDER BY file
""").show(20, truncate=False)

spark.sql(f"""
    SELECT e:type::string AS element_type, count(*) AS elements
    FROM {schema}.laws_parsed, LATERAL variant_explode(parsed:document:elements) AS t(pos, key, e)
    GROUP BY 1 ORDER BY 2 DESC
""").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sections and chunks: schema and samples

# COMMAND ----------

for table in ("laws", "laws_chunks", "laws_chunks_fixed"):
    df = spark.table(f"{schema}.{table}")
    print(f"{table}: {df.count()} rows")
    df.printSchema()
    df.drop("embedding").orderBy("law_number", "section").show(3, truncate=100)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunk sizes

# COMMAND ----------

SIZE_SQL = """
    SELECT '{name}' AS strategy, count(*) AS chunks,
           min(chars) AS min_chars, percentile(chars, 0.5) AS median_chars, max(chars) AS max_chars,
           round(avg(words)) AS avg_words, round(avg(chars) / 4) AS avg_tokens,
           count_if(chars / 4 > 512) AS over_512_tokens, count_if(words < 30) AS under_30_words
    FROM (SELECT length(text) AS chars, size(split(trim(text), '\\\\s+')) AS words FROM {schema}.{name})
"""
sizes = spark.sql(
    " UNION ALL ".join(SIZE_SQL.format(name=name, schema=schema) for name in ("laws_chunks", "laws_chunks_fixed"))
)
sizes.show(truncate=False)

spark.sql(f"""
    WITH c AS (
        SELECT law_number, first(law_title) AS law, count(*) AS section_chunks,
               round(avg(length(text))) AS avg_chars, max(length(text)) AS max_chars
        FROM {schema}.laws_chunks GROUP BY law_number
    ), f AS (
        SELECT law_number, count(*) AS fixed_chunks FROM {schema}.laws_chunks_fixed GROUP BY law_number
    )
    SELECT c.*, f.fixed_chunks FROM c JOIN f USING (law_number) ORDER BY law_number
""").show(20, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Smallest and largest section chunks

# COMMAND ----------

for order in ("ASC", "DESC"):
    spark.sql(f"""
        SELECT chunk_id, subheading, length(text) AS chars, pages, substr(text, 1, 160) AS start
        FROM {schema}.laws_chunks ORDER BY length(text) {order} LIMIT 3
    """).show(truncate=False)

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "sizes": [row.asDict() for row in sizes.collect()]}, default=str))
