# Referee AI: build plan

Staged plan for the Referee AI course project. Each stage ends with something checkable and is one pull request.
Stages 1–5 are the week 2 data work (due 21 Oct); stages 6–9 follow the course weeks.

Architecture: https://claude.ai/artifact/4UzwdQTspMLCQMTsc8ci8L

## Next steps (3 Nov)

1. Week 3 (lecture 3: MCP tool calling and agent orchestration): Stage 6, the agent with tools and memory, on a
   `week3` branch from `week1`. Its PR targets `week1` and is retargeted to `main` once #2 merges. The orchestration
   is with Maria for review; the Genie space and session memory don't depend on it, so they go first.
2. PR #2 is with Basak for review, posted on Discord on 28 Oct at 9am. It holds weeks 1 and 2 together, as Maria
   allowed because week 1 was late.
3. The course moved to a new workspace (`dbc-e81ca4d2-f6bd`) on 3 Nov. Done: profile re-pointed, jobs redeployed,
   Lakebase sync and table comments re-run, search experiment gives the same hit rates. Reply in the course channel.
4. Email FA contacts for past Laws of the Game exam questions as Excel or CSV, last season (2025/26) and this season
   so far, with permission to use them (draft written 28 Oct). Ask for: question_id, question, options,
   correct_answer, explanation, law_reference, season. Recheck older seasons against the 2026/27 changes. Keep the
   file in the volume, out of git.
5. Retrieval follow-ups from `retrieval_experiment.html`: hybrid search with `websearch_to_tsquery` or key terms.
   `MAX_CHUNK_WORDS` stays at 400 (an untuned guess, sized for a 512-token model; GTE takes 8,192). Tried 200 on
   28 Oct: 168 section chunks, same hit rates, the DOGSO handball question still misses 12.4. Sweep 100/200/400 once
   the FA questions give a bigger eval set; five questions can't separate them.
6. Stage 3: `law_changes` from the law changes file, and `scenarios` once the FA questions arrive, then their agent
   tools (`get_law_changes`, `find_similar_scenarios`).
7. `psycopg` crashes now and then on serverless while importing (SIGABRT loading `psycopg-binary`): `synced_tables`
   on 24 Oct, the search experiment on 3 Nov; both passed when re-run. No retry for now: re-run by hand.
8. Set up the Databricks VS Code extension with profile `llmops-course` and run something from it.

**Done so far:**

- PR #2, "Weeks 1–2", on branch `week1`: Stage 1, the `referee_ai` rename, the notebook fix and the PDF split.
- The PDF is split into 17 Laws plus the law changes in `data/laws/`, with `scripts/split_laws.py` reading the page
  ranges from the contents pages. No images; near-empty pages and six diagram pages (79, 88–90, 104, 117: signals,
  goal line, handball) are dropped, so what those diagrams show isn't in the text.
- Pages keep their original numbers as PDF page labels, and `data/laws/page_map.csv` maps each file page to its
  original page for citations.
- In Databricks: the 18 split PDFs are in `laws_files/raw/`, the full PDF in `laws_files/source/` and the page map at
  `laws_files/page_map.csv`. `laws_parsed` was rebuilt by running `notebooks/1_parse_laws.py` as a job: 18 files,
  101 pages, 772 elements, no errors, and the page counts match the page map.
- The ingest runs as a bundle job, `laws_ingest` (`resources/laws_ingest.job.yml`: parse, then split), validated,
  deployed to dev and run. It prints the schema and sample rows of `laws` and `laws_chunks`.
- `notebooks/3_gateway_experiment.py` asked the chat model five referee questions through the AI Gateway with no
  retrieval: 2 right, 1 right with a made-up quote, 2 wrong (old goalkeeper rule, invented page). Results in
  `gateway_experiment.html`.
- Databricks Connect works from the venv on serverless (`laws` read from VS Code's environment).
- Week 2 (in PR #2): lecture 2 config (`databricks-gte-large-en`, `lakebase_project_id`); a fixed-size
  chunking alternative (`laws_chunks_fixed`, 261 chunks) beside the section chunks (138); both embedded and synced to
  Lakebase (`SNAPSHOT`, no Change Data Feed); semantic, filtered and hybrid search compared in
  `retrieval_experiment.html` (fixed chunks 5/5 everywhere; section chunks 4/5 semantic, 5/5 filtered by Law).

## Stage 1: get the PDF into Databricks and parse it

1. The PDF is in the repo root, `Laws of the Game 2026_27_single pages.pdf` (260 pages, 22 MB). Keep it out of git: it is
   over the 1 MB pre-commit limit and IFAB-copyrighted.
2. Change `volume: "arxiv_files"` to `"laws_files"` in `project_config.yml` for all three environments, and update
   `tests/test_config.py` to match.
3. Create the volume and upload the PDF:

   ```bash
   databricks volumes create llmops_dev adambuckleyjones laws_files MANAGED -p llmops-course
   databricks fs mkdir dbfs:/Volumes/llmops_dev/adambuckleyjones/laws_files/raw -p llmops-course
   databricks fs cp "Laws of the Game 2026_27_single pages.pdf" dbfs:/Volumes/llmops_dev/adambuckleyjones/laws_files/raw/laws_of_the_game_2026_27.pdf -p llmops-course
   ```

4. Parse it in `notebooks/1_parse_laws.py`, on serverless:

   ```sql
   CREATE OR REPLACE TABLE llmops_dev.adambuckleyjones.laws_parsed AS
   SELECT path, ai_parse_document(content) AS parsed, current_timestamp() AS parsed_at
   FROM READ_FILES('/Volumes/llmops_dev/adambuckleyjones/laws_files/raw/', format => 'binaryFile');
   ```

5. Inspect the output: element and page counts, whether the "Law 1" to "Law 17" headings come out as separate elements,
   and what happened to the offside diagrams.

**Done when:** `laws_parsed` has one row, the text of Law 11 is readable in it, and you know what the headings look
like (Stage 2 depends on it).

**Status (14 Oct): done.** 260 pages, 1,742 elements, no errors. What the parse looks like:

- Each Law is a `title` element ("Offside"), preceded by a `text` element with the number ("Law11"). Page footers also
  carry it ("Law 11 | Offside").
- Sections are numbered `section_header` elements ("1. Offside position", "2. Offside offence"), so `Law 11.1` keys
  come straight from the headers.
- Section text continues across pages after `page_footer` and `page_number` elements, so assign text to sections by
  element order and drop footers, page numbers and figures.
- The 256 figures are mostly IFAB logos and photos, with no offside diagrams in Law 11.
- The course's `_extract_chunks` keeps only `text` elements and would lose every heading, so Stage 2 needs its own
  splitter.
- The PDF already contains "Outline summary of Law changes" (p166) and "Details of all Law changes" (p169–186), plus
  the glossary (p194–207) and the practical guidelines (p208 onwards).

## Stage 2: split it into sections

1. Add `src/referee_ai/laws_processor.py`, which splits the parsed elements by law and section heading.
2. Add a unit test with a small sample of parsed JSON, so the splitter is tested without Databricks.
3. Write two Delta tables: `laws` (one row per section: law, section, title, text, pages) and `laws_chunks` (one chunk
   per subheading block, prefixed with its law and section). The Laws are static, so both are rebuilt only for a new
   edition.

**Done when:** all 17 laws are present and `Law 12.3` returns the right text.

**Status (23 Oct): done, in PR #2.** `notebooks/2_split_sections.py` ran as a job: `laws` has 86 sections
across all 17 Laws and `laws_chunks` has 138 chunks, each with its original pages. In this edition 12.3 is "Corner
kick" (p119) and disciplinary action is 12.4. Law 6 has no section 6: the signals were on the dropped diagram pages.

## Stage 3: structured data

1. Fill `law_changes` from the "Details of all Law changes" pages of the same PDF (p169–186).
2. Build `scenarios.csv` with about 100 rows. Generate drafts with `gateway.chat`, then check each one by hand against a
   law section. Load it into the Delta table `scenarios`.

**Done when:** every scenario has a decision, a restart, a sanction and a reference to a law section.

Then the agent gets two more tools (Stage 6): `get_law_changes` on `law_changes` and `find_similar_scenarios` on
embedded `scenarios`.

## Stage 4: embeddings and search in Lakebase

1. Embed `laws_chunks` (and the alternative `laws_chunks_fixed`) with `databricks-gte-large-en` via `ai_query`, with
   `id` as the primary key.
2. Sync both to Lakebase as synced tables (`notebooks/5_synced_tables.py`, `SNAPSHOT`), with pgvector, an HNSW
   cosine index and a GIN full-text index.
3. Search them with `src/referee_ai/vector_search.py`: semantic, filtered by Law, hybrid.

**Done when:** both chunk tables are synced and indexed, and `notebooks/6_search_experiment.py` finds the expected
section in the top 3 for at least 4 of its 5 referee questions, with semantic search, on both tables.

**Status (24 Oct): done, in PR #2.** 138 and 261 rows synced, counts match Delta. Results in
`retrieval_experiment.html`. `scenarios` will be embedded the same way in Stage 3.
The earlier check, the query "handball on goal line", fails for section chunks (28 Oct): Law 1.10 and Law 16 rank
first on "goal line"; the first Law 12 chunk is 7th, 0.025 behind. Fixed chunks pass (`12.4-f15` 2nd). Same weakness
as the DOGSO miss: long section chunks dilute one specific sentence. Revisit with re-ranking and the FA eval set.

## Stage 5: make it reproducible

1. Bundle job `laws_ingest` (`resources/laws_ingest.job.yml`): parse, split and embed, then sync to Lakebase.
   Uploading the split PDFs stays a manual one-off step.
2. Rebuild everything from an empty schema:

   ```bash
   databricks bundle deploy -t dev -p llmops-course
   databricks bundle run laws_ingest -t dev -p llmops-course
   ```

**Done when:** the job rebuilds all tables and vectors from the PDFs in the volume.

**Status (24 Oct): done.** The job runs parse, split with embeddings, and the Lakebase sync on dev.

## Stage 6: agent with tools and memory (week 3)

Lecture 3 builds a tool-calling agent (`SimpleAgent` in the course notebooks, Chat Completions through the AI
Gateway), tools as custom functions or over MCP (UC functions, Genie) and session memory in Lakebase
(`LakebaseMemory`). Here the agent lives in `src/referee_ai/agent.py`, not a notebook, so it has unit tests and can be
served in week 5. Tools use only the data that exists today; `law_changes` and `scenarios` tools wait for Stage 3.

| Tool | Connection | Data | Use |
|---|---|---|---|
| `search_laws(query)` | custom Python function | `laws_chunks_synced`, through `LakebasePgVectorManager.search` | Find the passages for one part of a question, across all Laws |
| `get_law_section(section)` | UC SQL function over MCP | `laws` | Full text and pages of e.g. `12.4`, when a chunk is cut off |
| Genie space "Referee AI Laws" | Genie MCP | `laws`, `laws_chunks` (described by `7_table_comments`) | Structured questions: "list the sections of Law 12", "which sections are on page 119" |

No Law filter on `search_laws`: many questions span several Laws (handball on the line is Law 12 for the offence
and sanction, Law 14 for the penalty), so a wrong filter would hide the right section. In the retrieval experiment
the filter only helped when it was given the right Law.

Orchestration (proposed, to review with Maria): a fixed workflow with one model-directed step.

- **Code-controlled:** load the session's history from Lakebase, then always run `search_laws` on the whole
  question, so the model never answers a Laws question from memory (2 of 5 wrong in `gateway_experiment.html`).
  Pass the results to the model, run the tool loop (at most 6 iterations, fallback answer at the cap), save the
  question and the final answer, return it. Tool errors go back to the model as the tool result instead of failing
  the turn.
- **Model decisions:** split a multi-part question (decision, sanction, restart) into one `search_laws` per part
  when the first search doesn't cover every part; fetch a full section; ask Genie a structured question; reason
  over all the results and answer.
- **History:** only user questions and final answers are saved, not tool calls or results. It keeps history small;
  the model fetches tool results again when it needs them.
- **System prompt:** answer only from tool results, cite Law, section and page, and say when the Laws don't cover it.
- **Measured in Stage 7:** how often the model searches again on the FA questions and whether it changes accuracy,
  latency and tokens. If it rarely helps, drop the loop and keep a fixed RAG workflow.

Order: the Genie space and memory first, as they don't depend on the orchestration; the agent loop after review.

1. `resources/genie_space.yml`: the Genie space on `laws` and `laws_chunks`, with sample questions and instructions.
   Test it directly, then through Genie MCP.
2. `src/referee_ai/memory.py`: `LakebaseMemory` (`session_messages` table) from the course, imports changed to
   `referee_ai`. Test: save two messages in one session, read them back from a new instance, a second session stays
   separate.
3. `src/referee_ai/mcp.py` and `notebooks/8_uc_functions.py`: `ToolInfo`, `create_mcp_tools`, and `get_law_section`
   as a UC SQL function with comments (the model sees them through MCP), with a test call on `12.4`.
4. `src/referee_ai/tools.py` (`search_laws` tool) and `src/referee_ai/agent.py` (`RefereeAgent.answer(question,
   session_id)`), with `tests/test_agent.py` and `tests/test_tools.py` on a fake LLM client and in-memory history:
   first search always run, tool dispatch, tool errors, iteration cap, history loaded first, only the question and
   answer saved.
5. `notebooks/9_agent.py` and `resources/agent.job.yml` (UC functions, then the agent): a single-part question, a
   multi-part question, a structured question, an out-of-scope question, then a follow-up that needs the history
   ("and what is the restart?") from a new agent instance.
6. A PR `week3` → `week1` with the design choices above and a test plan.

**Done when:** the agent job answers the referee questions citing Law sections, splits the multi-part question into
more than one search, sends the structured question to Genie, declines the out-of-scope one, and a new agent
instance answers a follow-up from the history it loads from Lakebase.

**Status (3 Nov): design with Maria for review.** Genie space deployed to dev (`resources/genie_space.yml`) and
asked 5 questions through the Conversation API. The 4 structured ones were right, with the expected SQL (Law 12: 6
sections; page 119: 12.2, 12.3, 12.4; 12.4: 15 subheadings; sections and first page per Law). The match situation
("defender handles on the goal line") should have been refused, but Genie searched the `text` column with `ILIKE` and
answered (sending-off, penalty, 12.4 p124): the text instruction alone didn't stop it. Four paraphrased situations
tested whether Genie is good enough as RAG: 2 right (back-pass, wall distance), 2 wrong. "Keeper holds the ball too
long" got an indirect free kick, but it is a corner kick (12.3 p119). "Offside from a throw-in" was left undecided:
Genie picked sections 11.1, 11.2 and 15.1 itself and missed 11.3. Genie guesses keywords and a Law filter, and takes
19–36 s. Fix: `text` hidden in both tables so situations go to `search_laws`. Re-asked all 9: the 4 structured
answers are unchanged, and the 5 situations are declined (3 with no SQL; 2 point to the right sections: 12.1 and
12.4 p116/124, 13.2 p131–132). Reproducible as the `genie_space` job (`notebooks/8_genie_space.py`): run 797227736232012, same
results.

## Later stages

| Stage | Week | Work |
|---|---|---|
| 7 | 4 · 4 Nov | MLflow tracing, and evaluations that use `scenarios` as ground truth. Record a baseline accuracy. |
| 8 | 5 · 11 Nov | Serving endpoint and chat UI deployed through dev, acc and prd. |
| 9 | 6 · 18 Nov | Monitoring of traces, judges on live traffic, gateway cost. |

Demo day: 25 Nov.
