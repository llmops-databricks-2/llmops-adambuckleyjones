# Databricks notebook source
# ruff: noqa: ERA001
"""Describe the Laws tables and their columns in Unity Catalog, so Genie, the Assistant and agents can use them."""

# COMMAND ----------

# MAGIC %md
# MAGIC # Table and column comments
# MAGIC
# MAGIC Sets a comment on `laws_parsed`, `laws`, `laws_chunks` and `laws_chunks_fixed` and on each of their columns.
# MAGIC The ingest replaces these tables on every run, which can drop comments, so `laws_ingest` runs this job after
# MAGIC it. Fails if any column of these tables is left without a comment, e.g. a new column added to the ingest.

# COMMAND ----------

import json

from databricks.sdk.runtime import dbutils
from loguru import logger
from pyspark.sql import SparkSession

from referee_ai.config import load_config

dbutils.widgets.text("env", "dev")
cfg = load_config("project_config.yml", env=dbutils.widgets.get("env"))
spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

LAW_COLUMNS = {
    "law_number": "Number of the Law, 1 to 17 (e.g. 11 is Offside, 12 is Fouls and Misconduct).",
    "law_title": "Title of the Law, e.g. 'Fouls and Misconduct'.",
    "section": "Law and section as 'law.section', e.g. '12.4' is Law 12 section 4. '<law>.0' is the text before the "
    "Law's first numbered section, its introduction. Sort by law_number, not this string.",
    "section_title": "Title of the numbered section, e.g. 'Disciplinary action'; 'Introduction' for '<law>.0'.",
    "pages": "Page numbers in the original full Laws of the Game 2026/27 PDF (not the split files), for citations.",
}

CHUNK_COLUMNS = {
    "chunk_id": "Chunk identifier: '<section>-<n>' for section chunks, '<section>-f<n>' for fixed-size chunks.",
    **LAW_COLUMNS,
    "subheading": "Subheading inside the section the chunk comes from, e.g. 'Handling the ball'; null when the "
    "section has none, and always null in laws_chunks_fixed.",
    "text": "Chunk text, prefixed with its Law and section heading, e.g. 'Law 12 Fouls and Misconduct, "
    "12.4 Disciplinary action'. This is the text that is embedded and searched.",
    "pages": "Page numbers in the original full Laws of the Game 2026/27 PDF that this chunk's text comes from, "
    "for citations.",
    "id": "Primary key, a copy of chunk_id; the key of the Lakebase synced table.",
    "embedding": "1024-dimension embedding of text from databricks-gte-large-en, computed with ai_query. Compare "
    "with cosine similarity to a query embedded with the same model.",
}

COMMENTS = {
    "laws_parsed": (
        "One row per Laws of the Game 2026/27 PDF file (17 Laws plus the law changes) in the laws_files volume, "
        "with the raw ai_parse_document output. Input of the laws and chunk tables; built by the laws_ingest job.",
        {
            "path": "Volume path of the PDF file, e.g. .../raw/law_12_fouls_and_misconduct.pdf.",
            "parsed": "ai_parse_document output: document.pages, document.elements (type, content, page) and "
            "error_status.",
            "parsed_at": "When the file was parsed (UTC).",
        },
    ),
    "laws": (
        "IFAB Laws of the Game 2026/27, one row per numbered section of each Law (e.g. 12.4 Disciplinary action), "
        "with its full text and original page numbers. Built by the laws_ingest job from laws_parsed.",
        {
            **LAW_COLUMNS,
            "text": "Full text of the section, without its heading; subheadings and paragraphs separated by blank "
            "lines. Page headers, footers and page numbers removed.",
        },
    ),
    "laws_chunks": (
        "Retrieval chunks of the IFAB Laws of the Game 2026/27: one per subheading block within a numbered section, "
        "blocks over 400 words split at paragraph breaks. The chosen chunking; synced to Lakebase as "
        "laws_chunks_synced for semantic and hybrid search. Built by the laws_ingest job from laws_parsed.",
        CHUNK_COLUMNS,
    ),
    "laws_chunks_fixed": (
        "Alternative retrieval chunks of the IFAB Laws of the Game 2026/27: 500-character windows with 50 "
        "characters of overlap within each numbered section, ignoring subheadings and sentences. Kept to compare "
        "with laws_chunks; synced to Lakebase as laws_chunks_fixed_synced. Built by the laws_ingest job.",
        CHUNK_COLUMNS,
    ),
}


def quoted(text: str) -> str:
    """Quote text as a SQL string literal."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


# COMMAND ----------

columns = 0
for table, (table_comment, column_comments) in COMMENTS.items():
    fqn = f"{cfg.full_schema_name}.{table}"
    spark.sql(f"COMMENT ON TABLE {fqn} IS {quoted(table_comment)}")
    for column, comment in column_comments.items():
        spark.sql(f"ALTER TABLE {fqn} ALTER COLUMN {column} COMMENT {quoted(comment)}")
        columns += 1
    logger.info(f"{fqn}: table and {len(column_comments)} columns")

# COMMAND ----------

missing = spark.sql(
    f"""
    SELECT table_name, column_name FROM {cfg.catalog}.information_schema.columns
    WHERE table_schema = :schema AND table_name IN ({", ".join(quoted(t) for t in COMMENTS)}) AND comment IS NULL
    """,
    args={"schema": cfg.schema},
).collect()
if missing:
    raise ValueError(f"Columns without a comment: {[f'{r.table_name}.{r.column_name}' for r in missing]}")

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"status": "ok", "tables": len(COMMENTS), "columns": columns}))
