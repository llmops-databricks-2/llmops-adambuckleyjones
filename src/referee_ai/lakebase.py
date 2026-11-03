"""Connections to the project's Lakebase Postgres, shared by the vector store and session memory."""

import urllib.parse

import psycopg
from databricks.sdk import WorkspaceClient


def connect(workspace: WorkspaceClient, project_id: str) -> psycopg.Connection:
    """Open a connection to the project's first endpoint as the workspace client's identity, user or service principal.

    The password is a database credential fetched through the SDK, valid for an hour, so each connection gets a new
    one. A service principal's Postgres role is named after its application ID, which is its user_name.
    """
    postgres = workspace.postgres
    branch = next(iter(postgres.list_branches(parent=f"projects/{project_id}")))
    endpoint = next(iter(postgres.list_endpoints(parent=branch.name)))
    credential = postgres.generate_database_credential(endpoint=endpoint.name)
    user = workspace.current_user.me().user_name
    return psycopg.connect(
        f"postgresql://{urllib.parse.quote_plus(user)}:{credential.token}@{endpoint.status.hosts.host}:5432/"
        "databricks_postgres?sslmode=require"
    )
