"""Your first test: project_config.yml loads with the course's ProjectConfig for dev.

`ci.yml` runs every test under tests/ on each pull request and each push to main; add yours here.
"""

from pathlib import Path

from referee_ai.config import ProjectConfig

PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "project_config.yml"


def test_project_config_loads_for_dev() -> None:
    """Load the provisioned settings without requiring optional lecture resources."""
    cfg = ProjectConfig.from_yaml(str(PROJECT_CONFIG), "dev")

    assert cfg.full_volume_path == "llmops_dev.adambuckleyjones.laws_files"
    assert cfg.warehouse_id == "e9cda9338abe31cc"
    assert cfg.embedding_endpoint == "databricks-gte-large-en"
    assert cfg.lakebase_project_id == "lb-llmops-adambuckleyjones"
    assert cfg.usage_policy_id == "6bc3dda5-d72e-3084-9c1c-29a87a79fa27"
