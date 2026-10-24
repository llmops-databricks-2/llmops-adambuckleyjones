"""Semantic, filtered and hybrid search over a Laws chunk table synced to Lakebase, with pgvector.

Adapted from the course's LakebasePgVectorManager. The synced table is a read-only copy of a Delta chunk table
(laws_chunks or laws_chunks_fixed) whose embedding column is synced as a pgvector vector(1024).
"""

import os
import urllib.parse
from typing import Any

import psycopg
from databricks.sdk import WorkspaceClient
from loguru import logger

from referee_ai.config import ProjectConfig

RESULT_COLUMNS = "id, law_number, section, section_title, subheading, pages, text"


class LakebasePgVectorManager:
    """Search one synced chunk table in Lakebase. Credentials are short-lived and fetched through the SDK."""

    def __init__(self, config: ProjectConfig, synced_table: str, workspace: WorkspaceClient | None = None) -> None:
        self.config = config
        self.synced_table_name = synced_table
        # Synced tables land in a Postgres schema named after the Unity Catalog schema
        self.table_name = f'"{config.schema}"."{synced_table}"'
        self.workspace = workspace or WorkspaceClient()
        # Shared by the GIN index and the queries, so Postgres can use the index. Chunk text starts with its law,
        # section and subheading, so keywords in those match too.
        self.text_expr = "to_tsvector('english', text)"

    def _connection_string(self) -> str:
        """Build a connection string with a fresh database credential for the project's first endpoint."""
        postgres = self.workspace.postgres
        branch = next(iter(postgres.list_branches(parent=f"projects/{self.config.lakebase_project_id}")))
        endpoint = next(iter(postgres.list_endpoints(parent=branch.name)))
        credential = postgres.generate_database_credential(endpoint=endpoint.name)
        user = os.environ.get("DATABRICKS_CLIENT_ID") or self.workspace.current_user.me().user_name
        return (
            f"postgresql://{urllib.parse.quote_plus(user)}:{credential.token}@{endpoint.status.hosts.host}:5432/"
            "databricks_postgres?sslmode=require"
        )

    def connection(self) -> psycopg.Connection:
        """Open a Lakebase connection."""
        return psycopg.connect(self._connection_string())

    def ensure_extension(self) -> None:
        """Enable pgvector. Run before creating a synced table with a vector column: syncing doesn't install it."""
        with self.connection() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        logger.info("pgvector extension ready")

    def ensure_indexes(self) -> None:
        """Create the HNSW cosine index on the embedding and the GIN full-text index. Idempotent."""
        with self.connection() as conn:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self.synced_table_name}_embedding_hnsw "
                f"ON {self.table_name} USING hnsw (embedding vector_cosine_ops)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self.synced_table_name}_text_gin "
                f"ON {self.table_name} USING gin (({self.text_expr}))"
            )
        logger.info(f"Indexes ready on {self.table_name}")

    def embed_query(self, query: str) -> str:
        """Embed a query with the same model as the chunks, as a pgvector literal."""
        client = self.workspace.serving_endpoints.get_open_ai_client()
        vector = client.embeddings.create(model=self.config.embedding_endpoint, input=query).data[0].embedding
        return "[" + ",".join(str(float(value)) for value in vector) + "]"

    def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [description.name for description in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def search(self, query: str, num_results: int = 5, law_number: int | None = None) -> list[dict[str, Any]]:
        """Rank chunks by cosine similarity to the query, optionally only within one Law."""
        vector = self.embed_query(query)
        where, params = "", [vector]
        if law_number is not None:
            where, params = "WHERE law_number = %s", [vector, law_number]
        sql = f"""
            SELECT {RESULT_COLUMNS}, 1 - (embedding <=> %s::vector) AS score
            FROM {self.table_name} {where}
            ORDER BY score DESC LIMIT %s
        """
        return self._fetch(sql, [*params, num_results])

    def hybrid_search(
        self, query: str, num_results: int = 5, law_number: int | None = None, vector_weight: float = 0.7
    ) -> list[dict[str, Any]]:
        """Rank chunks by a weighted sum of cosine similarity and PostgreSQL full-text rank."""
        vector = self.embed_query(query)
        where, params = "", [vector, query]
        if law_number is not None:
            where, params = "WHERE law_number = %s", [vector, query, law_number]
        sql = f"""
            WITH ranked AS (
                SELECT {RESULT_COLUMNS},
                       1 - (embedding <=> %s::vector) AS vector_score,
                       ts_rank_cd({self.text_expr}, plainto_tsquery('english', %s)) AS text_score
                FROM {self.table_name} {where}
            )
            SELECT *, %s * vector_score + %s * text_score AS score
            FROM ranked ORDER BY score DESC LIMIT %s
        """
        return self._fetch(sql, [*params, vector_weight, 1 - vector_weight, num_results])
