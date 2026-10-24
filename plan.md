# Referee AI: build plan

Staged plan for the Referee AI course project. Each stage ends with something checkable and is one pull request.
Stages 1–5 are the week 2 data work (due 21 Oct); stages 6–9 follow the course weeks.

Architecture: https://claude.ai/artifact/4UzwdQTspMLCQMTsc8ci8L

## Next steps (24 Oct)

1. Set up the Databricks VS Code extension with profile `llmops-course` and run something from it.
2. Email FA contacts for past quiz questions as CSV, with permission to use them. Ask for: question_id, question,
   options, correct_answer, explanation, law_reference, season. Recheck older seasons against the 2026/27 changes.
3. Get PR #2 (weeks 1–2) and the week 2 PR reviewed; retarget the week 2 PR to `main` once #2 merges.
4. Retrieval follow-ups from `retrieval_experiment.html`: hybrid search with `websearch_to_tsquery` or key terms, and
   section chunks with a lower word limit so long blocks like DOGSO are split.
5. Stage 3: `law_changes` from the law changes file, and `scenarios` once the FA questions arrive.
6. Lecture 3 (28 Oct), already in `course-code-hub`: agent, MCP tools, memory, evaluation, serving (Stage 6).

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
- Week 2 (branch `week2`): lecture 2 config (`databricks-gte-large-en`, `lakebase_project_id`); a fixed-size
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

## Stage 4: embeddings and search in Lakebase

1. Embed `laws_chunks` (and the alternative `laws_chunks_fixed`) with `databricks-gte-large-en` via `ai_query`, with
   `id` as the primary key.
2. Sync both to Lakebase as synced tables (`notebooks/5_synced_tables.py`, `SNAPSHOT`), with pgvector, an HNSW
   cosine index and a GIN full-text index.
3. Search them with `src/referee_ai/vector_search.py`: semantic, filtered by Law, hybrid.

**Done when:** the query "handball on goal line" returns Law 12 sections in its top 3 results.

**Status (24 Oct): done, on `week2`.** 138 and 261 rows synced, counts match Delta. Results in
`retrieval_experiment.html`. `scenarios` will be embedded the same way in Stage 3.

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

## Later stages

| Stage | Week | Work |
|---|---|---|
| 6 | 3 · 28 Oct | The four tools (`search_laws`, `find_similar_scenarios`, `get_law_section`, `get_law_changes`) and the agent loop. Test them in a notebook first. |
| 7 | 4 · 4 Nov | MLflow tracing, and evaluations that use `scenarios` as ground truth. Record a baseline accuracy. |
| 8 | 5 · 11 Nov | Serving endpoint and chat UI deployed through dev, acc and prd. |
| 9 | 6 · 18 Nov | Monitoring of traces, judges on live traffic, gateway cost. |

Demo day: 25 Nov.
