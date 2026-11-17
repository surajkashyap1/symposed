# The update pipeline (Samarth, 2026-10-25)

Replaces `spec-gap-mining-v2.md`. The pipeline finds systematic reviews that are
due an update and writes the guide for the one Samarth picks. Step numbers here
are the ones used in conversation and in the Update Mining Flow diagram.

1. **Registry copies up to date.** The local PROSPERO and OSF copies must cover
   the last 10 days. Testing runs may skip both (`SKIP_REGISTRY_MIRRORS=true`);
   every output then says the registries were not checked.
2. **Topic.** The topic terms from the proforma. There may be one or several.
   Each term is searched on its own: no complex search strategy is built.
3. **Find systematic reviews.** At least 50 (`REVIEW_COUNT`), most relevant
   first, with two filters:
   1. published more than 3 years ago (`REVIEW_MIN_AGE_YEARS`). The search
      date is ignored here;
   2. not already updated. No later systematic review repeats its work, and no
      update is under way on PROSPERO or OSF. This is the novelty check.
4. **Full texts.** Samarth provides the full text of every review that passes
   step 3. The search date used for paper selection, the search strategy and
   the inclusion criteria are pulled out of the full texts.
5. **Eligible studies per update.** Using each review's own search strategy and
   inclusion criteria, count the eligible studies published since its search
   date, and present the count for each review's update.
6. **Pick.** Samarth looks at the eligible studies (PMIDs) for a few updates,
   decides whether they suit a guide, and picks one.
7. **Recall test.** Backtest the search strategy the guide will use (the
   original review's, perhaps slightly modified to capture more papers): does
   it find the studies the original review included?
8. **The guide.** Everything originally planned for the guide, unchanged. The
   pipeline has the original review's full text, which makes the guide specific
   and a true update of it.

## The two agentic filters (Samarth, 2026-10-27)

- **Step 3b, triage**, runs after step 3 and before step 4 asks for full texts.
  Opus reads every review that passed step 3 (abstract and metadata), searches
  PubMed, the web and earlier Symposed assessments itself, and shortlists five
  options. Each is a direct update or a reworked angle (location, population,
  focus, implementation, method). Step 4 then asks only for those five full texts.
- **Step 5b, appraisal**, runs after step 5 has counted the shortlisted direct
  updates. Opus reads the full texts and the step 5 counts, searches again,
  and selects one option with its title, PICO, criteria and PubMed search.
- Step 6 shows Step 5b's selection. Picking it runs steps 5, 7 and 8 on its own
  search and criteria. An alternative angle counts every record, not only those
  since the original search, and skips the recall test, since the original's
  included studies fall outside the new question. Picking another PMID writes
  that review's direct update, as before.

The prompts are `src/guide_pipeline/prompts/stage1_triage_prompt.md` and
`stage2_fulltext_appraisal_prompt.md` (or `AGENT_PROMPTS_DIR`). They are read
fresh every time a stage runs, so they can be edited without touching code.
Only the text after the `=== PROMPT START ===` line is sent. Each finished stage
is saved as `stage1.json` or `stage2.json` with `STAGE1.md` or `STAGE2.md` and a
transcript, and reused on the next run: delete the file to run the stage again.
Every option either stage assessed is kept in the `triage_records` table of
`data/mining.sqlite`, which the agents read back through `db_lookup`.

Rule 1: every PubMed hit count the agents report is compared with what the
`pubmed_search` tool returned (a wrong count is replaced and the change listed),
and every competing review is checked against the PMIDs and URLs the tools
returned. Anything not found is marked unverified in the stage file.

Models: the stages run on `ANTHROPIC_DECISION_MODEL` (Opus 5.5 or higher, with no
fallback to a smaller model). Basic searching and retrieval run on Haiku 5.5:
step 4 extraction, step 5 translation and screening, and step 7 revisions. The
guide (step 8) runs on Sonnet 5.5. The step 3 novelty judge stays on Opus.

## How it is built

| Step | Code | Notes |
|---|---|---|
| 1 | `mining/pipeline.py` | `ensure_fresh` on both mirrors; skipping is recorded |
| 2 | `mining/reviews.py: topic_terms` | split on commas, semicolons, new lines |
| 3.1 | `mining/reviews.py: find_reviews` | `systematic[sb]`, publication date before the cutoff, each term's best in turn |
| 3.2 | `mining/reviews.py: check_already_updated` | one PubMed title-word search with the systematic review filter, published since the review; the 5 closest read with abstracts, plus the 3 closest PROSPERO and OSF registrations since (local mirrors); Opus 5.5 at medium effort gives a decision only, no rationale (task `update_check`, Samarth 2026-10-27); batches of 25 until 30 pass |
| Step 3b, Step 5b | `mining/agent.py` | Opus tool loop: `pubmed_search`, `pubmed_fetch`, `db_lookup`, server `web_search` and `web_fetch`; context editing clears old tool results; per stage tool and dollar budget |
| 4 | `mining/extract.py` | Haiku; quotes for the date and count and every strategy checked against the text |
| 5 | `mining/count.py` | strategy translated to PubMed (MeSH checked); records added to PubMed after the search ended; every hit screened by abstract; budget pause |
| 6 | `updates papers`, `updates pick` | `UPDATES.md`, `updates.json`, `pick.json` |
| 7 | `mining/recall_check.py` | included studies matched to PubMed; search recall 90%, screening recall 95%; up to 2 revisions |
| 8 | `mining/guide.py` | the existing guide (`guide_content.assemble`) with the original's criteria and the tested search |

## Choices made where the steps leave room

- "Since its search date" is PubMed's entry date (records added after the
  search ended), the usual cut point for an update. A review with no search
  date in its text uses its publication date, marked estimated.
- A review whose full text has no search strategy (often it is in a
  supplement) gets a search built from its criteria, marked in the table.
- Screening is by title and abstract. Possibly eligible = likely eligible +
  unclear. The step 5 table marks updates with fewer than 6 ("more than 5").
- A search with more than 3,000 new records is flagged as too broad, not screened.
