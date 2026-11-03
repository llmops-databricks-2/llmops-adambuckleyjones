"""Conversation history per session in Lakebase, so a follow-up question can use the earlier turns.

Adapted from the course's LakebaseMemory. The agent saves only each question and its final answer, not tool calls or
tool results. Errors raise instead of returning an empty history, which would look like a new session.
"""

from typing import Any

import psycopg
from databricks.sdk import WorkspaceClient
from loguru import logger
from psycopg.types.json import Jsonb

from referee_ai.config import ProjectConfig
from referee_ai.lakebase import connect


class LakebaseMemory:
    """Save and load the messages of a session in the session_messages table.

    Connects as the identity of the workspace client: a service principal in jobs and serving, so sessions are only
    kept apart by session_id. The caller must make session IDs unguessable and tie them to the user.
    """

    def __init__(self, config: ProjectConfig, workspace: WorkspaceClient | None = None) -> None:
        self.config = config
        self.workspace = workspace or WorkspaceClient()

    def connection(self) -> psycopg.Connection:
        """Open a Lakebase connection."""
        return connect(self.workspace, self.config.lakebase_project_id)

    def ensure_schema(self) -> None:
        """Create the session table and its session_id index. Idempotent."""
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_messages_session_id ON session_messages(session_id)")
        logger.info("session_messages ready")

    def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Load a session's messages, oldest first. Empty for a new session."""
        with self.connection() as conn:
            rows = conn.execute(
                # Ordered by id: messages saved together share created_at, which would let them come back reordered.
                "SELECT message_data FROM session_messages WHERE session_id = %s ORDER BY id",
                (session_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def save_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """Append messages to a session, in one transaction."""
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO session_messages (session_id, message_data) VALUES (%s, %s)",
                [(session_id, Jsonb(message)) for message in messages],
            )
        logger.info(f"Saved {len(messages)} messages to session {session_id}")
