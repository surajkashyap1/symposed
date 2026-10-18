# Symposed Guide Pipeline (v1)

A Python script you run by hand. It takes **one guide request** (the proforma
answers) and produces a per-request folder containing a JSON of everything it
found and a draft Word document of the guide. Every output is reviewed by a human
and PROSPERO is checked manually before anything reaches a customer.

v1 data sources only: **PubMed** (NCBI E-utilities), **Europe PMC**,
**ClinicalTrials.gov** (API v2). No PROSPERO mirror, dashboard, database, or
scheduler yet — those come back later, one at a time.

## Build plan (one step per session)

- **Step 0 — Setup** *(this step)*: repo, `CLAUDE.md`, env vars for API keys,
  settings module, per-request output folder. ✅
- **Step 1 — API clients**: PubMed, Europe PMC, ClinicalTrials.gov with rate
  limiting, retry+backoff, and response caching. Test: a query prints a count
  matching the website. ✅ (`python -m guide_pipeline counts "<query>"`)
- **Step 2 — Concept mapping & landscape**: proforma topic → real MeSH terms via
  E-utilities; four counts (total literature, publication years, existing
  systematic reviews, existing guidelines). ✅ (`python -m guide_pipeline landscape "<topic>"`)
- **Step 3 — Candidates & gates**: LLM makes 8–12 candidate titles across the
  spec's 14 gap axes; count-only queries; apply gates; rank survivors. ✅
  (`python -m guide_pipeline candidates "<topic>"`)
- **Step 4 — Deep retrieval**: chosen title only — full records + abstracts,
  dedupe (DOI → PMID → title+year), tag each paper with a suggested use. ✅
  (`python -m guide_pipeline retrieve "<pubmed query>"`)
- **Step 5 — The guide**: draft the Word doc from retrieved records only,
  including the date the searches were run. ✅
  (`python -m guide_pipeline guide "<title>" -- "<pubmed query>"`)

## Aligning with the full build spec

v1 above was the cut-down slice. We are now aligning it with the full
*Symposed Pipeline Build Spec v1.1*, still one step per session:

- **A1 — Stage 2 generation + taxonomy** ✅: the 14 gap axes (weighted to 3/4/12/13),
  ≥6 axes and ≤2 per axis enforced in code (with a top-up call for unused axes),
  two-person rule, new batch with rejected titles as negative context when none
  pass (§1.2), and the fixed 5-category suggested-use taxonomy (§6.3).
- **A2 — PROSPERO adapter** ✅: local SQLite mirror (FTS5 shortlist + trigram
  similarity), full harvest, weekly delta, manual export import, staleness guard,
  per-check record of dates + search terms (§3). All acquisition is in
  `prospero/adapter.py` — a proper CRD feed replaces that one file.
- **A3 — Stage 3/4 gates** ✅: three count queries per candidate from one
  concept query (records to screen / eligible primary studies / recent SRs),
  published protocols via PubMed, trials completing within 12 months, PROSPERO
  mirror check. Gates in `gates.py` with outcome + value + threshold each:
  REJECT / DOWNGRADE (scoping or narrative) / FLAG / PASS. Every search recorded.
  (Heterogeneity gate needs abstracts → moves to A5.)
- **A4 — Per-task model routing + Claude provider** ✅: Claude Sonnet 5 for every
  task, effort + thinking per task (`llm.TASKS`, from the table in
  `docs/spec-update-screening.md`), overridable per task via `MODEL_<TASK>` /
  `EFFORT_<TASK>` / `THINKING_<TASK>`. Structured outputs enforce each call's JSON
  schema (axes limited to the 14). Every run prints tokens and dollar cost.
- **A5 — Stage 5 v2 (spec update)** ✅ (Batch API → A5b): criteria writing,
  attribute extraction, full-recall screening (likely eligible / likely
  ineligible / unclear, check full text + reason + evidence basis), Europe PMC
  open-access full text, DOI list for unclear-without-OA, heterogeneity gate.
  Recall + consistency harnesses (`recall_fixtures/`, history in
  `recall_fixtures/history.jsonl`). First fixture: 19/19 and 18/19 recall at the
  final settings; 0 eligible/ineligible flips; 17/20 non-included papers marked
  likely ineligible. Needs 2–3 more known reviews from Samarth.
- **Run + feedback metrics** ✅: `request.py` turns any website proforma into a
  request (review type and flexibility, topic or BLANK topic starting from the
  specialties, team size, a plain description of the user so questions stay
  feasible); `run.py` runs one request end to end and appends ~40 metrics per
  guide to `output/metrics.jsonl` (request shape, per-gate outcomes, pass rate,
  axes, papers, full-text share, status counts, cost by task, cost per paper,
  seconds per stage). `metrics` summarises blank-topic vs topic-given runs.
- **A5b — Batch API** ✅: screening runs in two rounds (attributes, then
  screening), each submitted as one Message Batch at half price. Default for all
  runs (`LLM_BATCH=true`); `--sync` switches to parallel calls for quick tests.
  Batches usually finish in minutes, at most 24 hours, well inside the 7-day
  turnaround. Failed/expired requests in a batch keep their paper as unclear.
- **A6 — Stage 4b scoring + Stage 5 re-score + 5b tie break** ✅ (`scoring.py`):
  six component scores from API counts and the proforma (workable 12-40 band,
  recency, rationale, alignment with the user's topic, feasibility against the
  team's cap, distance from the nearest protocol), configurable weights
  (`SCORE_WEIGHT_<NAME>`), margin and max tied. A clear leader is screened alone;
  up to 3 tied candidates are each screened, re-scored on what screening found,
  and only if still tied does the model choose (max effort), with its rationale
  per criterion stored, a reviewer override field, and unchosen candidates kept.
- **A7 — Database schema** (§5 tables, unique normalised-title index) + Sheets sync.
- **A8 — More sources** ✅ (partly): Europe PMC preprints as a second retrieval
  source (PubMed queries translated to Europe PMC syntax, verified against
  PubMed counts); OpenAlex for the landscape's year distribution (one call);
  Crossref DOI gap-filling (accepted only on a close title and year match).
  Not yet: Semantic Scholar and CORE (need free API keys), WHO ICTRP (no public
  API, bulk export only).
- **A9 — Full 26-section guide** ✅ (`guide_content.py` + `guide.py`): sections in
  the spec's order, verbatim novelty statement, registration urgency and
  disclaimers plus the website's acknowledgement and AI note. Built by code:
  PICO, feasibility, papers table, RoB tool and reporting guideline for the
  design, PRISMA counts, timeline from the user's hours, search appendix.
  Written by the model and checked by code: search strategies (each run in
  PubMed for a real count; MeSH terms looked up; a zero-record strategy is
  never recommended), protocol (may cite only supplied records; invented
  citation numbers are removed), PROSPERO entry. Literature and narrative
  reviews get their own section set. Reviewer warnings go to results.json.
- **A10 — Stage 6 verification screen + weekly batch scheduler.**
- **Guide v2 — designed PDF + companion files** ✅ (Suraj's brief, 2026-10-17):
  `guide_model.py` builds one JSON render model (saved as `guide_model.json`);
  `guide_pdf.py` renders it with WeasyPrint from `assets/guide.html.j2` +
  `assets/guide.css` (claret cover with the mark, contents with page numbers,
  watermark on every page, a full width coloured banner per numbered step, red
  boxes for disclaimers, nothing below 7pt); `diagrams.py` draws the timeline,
  include or exclude decision tree, risk of bias tree and PRISMA flow as SVG;
  `screenshots.py` captures each numbered search in PubMed (Playwright);
  `companions.py` writes `tracker.xlsx` (screening with drop downs, extraction,
  risk of bias, search log), `protocol.docx` and `prospero_draft.docx`;
  `deliver.py` zips them as `guide-pack.zip` (stored in `guide_runs.guide_docx`).
  Step names live only in `guide_model.steps()`. House style for user-facing
  text: plain English, no semicolons, no dashes (`plain.tidy`, checked by tests).
  Papers show no rating: only likely eligible or unclear papers are listed, with
  PubMed's own publication type or our marked estimate. Re-render after a design
  change with `python -m guide_pipeline render <run folder> [--shots]`.
- **Guide v2, step 3: review led discovery** ✅ (`discovery.py`, `llm_cache.py`):
  topics one or two levels inside the specialty, each counted in PubMed (reviews
  and primary studies, last 10 years), fewest reviews first; the closest reviews
  on the topic are read in full (Europe PMC open access and open access PDFs
  listed by OpenAlex fetched automatically, the rest supplied by hand); the decider turns their gaps into questions, which
  go through the usual gates, with the 14 axes as a lens only when a gap
  question is not new enough; the next topic only if no real gap. After scoring,
  a final check reads the 2 or 3 reviews closest to the title and asks: new,
  publishable as a review, realistic? Reader Sonnet 5.5, decider Opus 5.5.
  `DISCOVERY_MODE=axes` restores the v1 method.

- **Guide v2, step 4: two alternatives and the swap** ✅ (`alternatives.py`):
  every guide ends with a shortlist page of the next two best scored questions
  that passed the gates (PICO, why it matters, why it is new, eligible studies,
  screening volume, best search, PROSPERO check date) and the offer: switch
  within 30 days for £5. Alternatives are stored in `guide_title_registry` with
  status `alternative` and held for that customer for 30 days. On a swap:
  `python -m guide_pipeline swap <run folder> <1|2> [--save]` re-runs the gates
  and PROSPERO check today and only then writes the full guide.

- **Pick before the guide** ✅ (`shortlist.py`, Samarth 2026-10-18): after
  scoring, a review led run stops with the top 3 questions in
  `output/discovery/<order>/SHORTLIST.md` and `shortlist.docx` (title, project
  brief, PICO, why it matters, why it is new, scope). A crowded first topic is
  topped up from the next two topics through the axes (no extra full texts).
  `python -m guide_pipeline pick <order> <n>` records the pick, then run again:
  only the pick gets the final check (it may ask for 2 or 3 full texts), and if
  it fails the shortlist comes back with it marked. The other options become the
  guide's alternatives. `PICK_BEFORE_GUIDE=false` restores the automatic choice.
- **Journal novelty check** ✅ (`novelty.py`, Samarth 2026-10-18): before a
  question reaches the shortlist, the decider (Opus 5.5, maximum effort, 64k
  reply budget, streamed) reads the abstracts of the closest reviews of any
  kind and the closest recent primary studies, labels each one's overlap, and
  judges as an editor would: novel, not novel, dead (new but unlikely to give a
  useful answer) or uncertain. Only novel and uncertain questions are shown,
  each with its closest papers listed for a person to verify; the next best
  question is checked until three pass (`NOVELTY_MAX_CHECKS`).

## Supplying full texts

A review led run first fetches what it can itself: Europe PMC open access
text, then the open access PDF OpenAlex lists for the DOI (saved as
`<PMID>.oa.pdf`, kept only if its text names the review). The download names the
pipeline in its User-Agent and gives up when a publisher refuses, so free papers
on some publisher sites still come to a person. It stops when it needs the rest:

```bash
python -m guide_pipeline run output/requests/<order>.json
#  PAUSED: 2 full text(s) needed ... see output/discovery/<order>/fulltexts/NEEDED.md
```

Save each listed review in that folder as `<PMID>.docx` (pasted text is fine),
`.pdf`, `.txt` or `.md`, or an empty `<PMID>.skip` if you cannot get it (its
abstract is used). A file only counts if text can be read from it: a scanned
PDF has none, and the run asks for the text pasted into Word instead. Run the same command again: everything before the pause is
replayed from cache at no cost. `--abstracts-ok` uses abstracts for anything
still missing instead of pausing. The Friday `batch` does the same per order:
a paused order gets no run row and is picked up again next time.

Model (decided 2026-09-25): **Claude Sonnet 5 for every task**, reasoning effort
set per task. Groq proved too weak (narrow searches, flaky JSON) and stays only as
a free local option (`LLM_PROVIDER=groq`). First live run: a two-batch candidate
screen cost about $0.13.

## PROSPERO mirror

PROSPERO has no public API. The mirror is filled from the undocumented endpoint
behind its search page (the same call the web UI makes), in exports of up to
10,000 records, spaced 3 s apart. CRD have been asked for a proper feed or
permission; until then, `import` is the manual fallback and merges identically.

```bash
python -m guide_pipeline prospero harvest          # once, at setup (~500k records, ~1 h)
python -m guide_pipeline prospero refresh          # weekly, before the batch (Friday)
python -m guide_pipeline prospero import export.txt  # manual fallback: the UI's download file
python -m guide_pipeline prospero status           # size, coverage, fresh or STALE
python -m guide_pipeline prospero check "<title>"  # fuzzy match: REGISTERED / REVIEW / CLEAR
```

Checks refuse to run if the mirror covers registrations more than
`PROSPERO_MAX_AGE_DAYS` (10) old.

Matching is lexical (word shortlist + trigram similarity). Calibrated on the full
register: light rewordings score ~0.80 and auto-reject (>= 0.75); heavier
rewordings and close-but-different questions both land ~0.55-0.70, so everything
>= 0.45 is surfaced as REVIEW for a human rather than auto-decided. Synonym-heavy
duplicates ("paediatric ICU" for "critically ill children") can score below 0.45
— which is why the human's live PROSPERO check on the shipped title stays.

Harvest quirks handled: withdrawn protocols have no public title and are skipped
(~145); one bulk-migration day (2020-04-28, 10,676 records) exceeds the export cap
and is split by accession-number prefix. The public export has titles, IDs and dates
only — status, condition and outcomes stay empty until a proper feed exists.

## Setup

```bash
cd guide-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # then fill in the keys
```

Get the keys:
- **NCBI API key** (free): https://www.ncbi.nlm.nih.gov/account/ → Settings → API Key Management
- **Anthropic API key**: platform.claude.com -> API keys (billed separately from
  any Claude subscription; set a monthly spend limit)
- **Groq API key** (optional, free local trials): https://console.groq.com/keys

## Run

```bash
guide-pipeline          # setup check ("doctor"): shows which keys are set, creates output/
# or:  python -m guide_pipeline

python -m guide_pipeline counts "vitamin d AND sepsis"   # Step 1 live smoke: prints each
                                                         # source's count to compare to the website
python -m guide_pipeline landscape "vitamin d deficiency"  # Step 2: MeSH terms + the four
                                                           # landscape counts (total/by-year/SRs/guidelines)
python -m guide_pipeline candidates "vitamin d deficiency in critically ill adults"  # Step 3:
                                                           # LLM candidate titles, count-gated and ranked
python -m guide_pipeline retrieve "vitamin D[tiab] AND critically ill[tiab] AND randomized[tiab]"  # Step 4:
                                                           # full records + abstracts, deduped, use-tagged
# the old `guide "<title>" -- "<query>"` command was replaced by `run` (below)
```

## Run a whole request

```bash
python -m guide_pipeline run output/requests/<order>.json [--limit N]   # proforma in, draft guide + metrics out
python -m guide_pipeline metrics                                        # averages across all runs
```

The request file is the website's proforma answers, bare or as
`{"order_id": ..., "proforma": {...}}`. Request files and outputs stay in the
gitignored `output/` folder: they contain customer answers.

## Test

```bash
pytest                                  # offline, fake model calls, costs nothing
python -m guide_pipeline recall recall_fixtures/vitamin-d-icu-mortality.json [--others 20]
python -m guide_pipeline consistency recall_fixtures/vitamin-d-icu-mortality.json --papers 8
```

A recall fixture is a published review whose included studies are known: its own
criteria (transcribed), the included PMIDs (from the paper itself), and its search
query. See `recall_fixtures/vitamin-d-icu-mortality.json` for the format. Recall
and consistency runs call the model (roughly $0.40 and $0.30 each).
