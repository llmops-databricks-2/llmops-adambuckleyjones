# llmops-adambuckleyjones

Your repository for the LLMOps course on Databricks. Everything you need in
the course workspace was provisioned for you before you got this repo, and every id is already in
`project_config.yml`: you configure nothing.

## Referee AI

The project in this repo: an assistant that helps football referees and referee exam candidates answer questions on
the IFAB Laws of the Game 2026/27, citing the Law, section and page. Progress and next steps are in `plan.md`
(also `plan.html`); the first model experiment is in `gateway_experiment.html`.

- `scripts/split_laws.py` splits the Laws PDF into one PDF per Law plus the law changes, and writes
  `data/laws/page_map.csv` so citations use the original pages.
- The `laws_ingest` job (`resources/laws_ingest.job.yml`) parses the split PDFs (`notebooks/1_parse_laws.py`) and
  writes the `laws` and `laws_chunks` tables (`notebooks/2_split_sections.py`).
- `src/referee_ai/laws_processor.py` holds the section and chunk logic, tested in `tests/test_laws_processor.py`.

## Join the course Discord

Join the course's Discord server with this invite link:
[https://discord.gg/V4XRYcBFDE](https://discord.gg/V4XRYcBFDE). Join under the
Discord username you wrote in the intake form: the course channels open automatically for members
on the student list.

## What was provisioned for you

| What | Value |
|---|---|
| Your schema in development, which you manage | `llmops_dev.adambuckleyjones` |
| Your schema in acceptance, which you read | `llmops_acc.adambuckleyjones` |
| Your schema in production, which you read | `llmops_prd.adambuckleyjones` |
| Volume (created in week 1) | `laws_files`, such as `llmops_dev.adambuckleyjones.laws_files` |
| SQL warehouse id | `e9cda9338abe31cc` |
| Usage policy id | `6bc3dda5-d72e-3084-9c1c-29a87a79fa27` |
| MLflow experiments | Dev: `/llmops/adambuckleyjones-dev`; acc: `/llmops/adambuckleyjones-acc`; prd: `/llmops/adambuckleyjones-prd` |
| Chat model service | `course_ops.gateway.chat` |
| Embedding model service | `course_ops.gateway.embed` |

Both settings name model services of the course’s AI Gateway, with a monthly budget per student.
Chat routes to GPT-OSS-120B; embeddings route to GTE Large. Call both through the gateway
with the `databricks-openai` package:

```python
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(use_ai_gateway=True)
client.chat.completions.create(
    model="course_ops.gateway.chat",
    messages=[...],
    reasoning_effort="low",
    max_tokens=1024,
)
client.embeddings.create(model="course_ops.gateway.embed", input="A paper abstract")
```

The `databricks-openai` package is not included in this repo’s dependencies. The same APIs
are available through the installed `openai` client with the workspace base URL
`/ai-gateway/mlflow/v1` and Databricks authentication.

`embedding_endpoint` is a gateway model service despite the existing field name. Generate
vectors through its embeddings API before storing them in pgvector. It is not a managed
Vector Search index’s `embedding_model_endpoint_name`.

## Lakebase

The `lakebase_instance` value in `project_config.yml` identifies your Lakebase project.
All three environments share it; your Unity Catalog schemas remain separate.
Onboarding does not create an application database or install pgvector. Create the database
and extensions you need during the course. A Vector Search endpoint is not provisioned.

For a dedicated student project, you and your three deployment service principals have project
management access and OAuth Postgres roles with database administration privileges. The project
carries your usage policy and student cost tag. Its initial compute range is 0.5–2 CU, with
suspension after five idle minutes. Creating extra branches or computes can increase its cost.

## What is in the repo

- `src/referee_ai/`: starts with `config.py`, which loads `project_config.yml`.
  Add the other course modules as you work through the lectures.
- `lecture_1/`, `lecture_2/` and so on, when you add them: copy a lecture's folder from the course
  code as it is, to the root of this repo, where its notebooks find `project_config.yml` one level up.
  Commit it with the hooks installed (below): the first commit stops once, after the hooks have
  formatted the notebooks and fixed what ruff can, and goes through when you add their changes and
  commit again. Ruff rules are configured in `pyproject.toml`.
- `databricks.yml` and `resources/`: the bundle, with three targets, `dev` (your sandbox, in
  development mode, the default), `acc` and `prd`. It builds the package as a wheel with `uv build`
  and deploys the `hello` job, named after its target (`job-hello-adambuckleyjones-dev`,
  `-acc`, `-prd`), one serverless notebook task that installs the wheel and writes one row to the
  `hello` table of your schema in the target's catalog, such as
  `llmops_dev.adambuckleyjones.hello`. The course's onboarding
  does not deploy these jobs yet. Deployment workflows are introduced in a later lecture.
- `pyproject.toml` and `version.txt`: the package and its version, bumped as the lectures ask.
- `tests/`: your tests; `test_config.py` checks that `project_config.yml` loads.
- `.github/workflows/ci.yml`: on every pull request and push to `main`, installs the package with
  uv and runs the pre-commit hooks and the tests.
- `.github/CODEOWNERS`: who reviews a pull request to `main`, which needs one approving review.

## Getting started

```bash
uv sync --extra dev
uvx pre-commit install
databricks bundle validate -t dev
```

Each environment logs to its own MLflow experiment and UC trace tables in its matching catalog. You can manage the dev experiment and write dev traces; acc and prd are read-only for you. Each deploy service principal manages its own environment’s experiment and writes to that environment’s schema.
