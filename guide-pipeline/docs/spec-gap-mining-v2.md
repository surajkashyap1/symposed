> **Superseded on 2026-10-25** by `spec-update-pipeline.md`. Kept for reference only: do not build from this file.

# Pipeline change: gap mining v2 (testing mode)

## How to work on this

1. Read CLAUDE.md, the existing pipeline code in guide-pipeline, and the spec documents in docs before writing anything. Then propose an implementation plan split into the milestones at the end of this document. Do not start coding until the plan is approved.
2. Build one milestone at a time. Each milestone has acceptance tests. Write and run them before moving on.
3. Do not delete the existing candidate generation code (generating questions across axes, then testing novelty). Keep it behind a config option CANDIDATE_SOURCE, with values "mined" (new default) and "generated" (existing approach, kept as a fallback).
4. Add a TESTING_MODE flag, on by default. In testing mode the pipeline never generates guides. It produces the evaluation report described below.

## Rules that still apply

- Every citation, PMID, DOI, NCT number, title, date and count must come from an API response or a provided document. The model never supplies these from its own knowledge.
- No general web search anywhere in the pipeline.
- Every screening outcome is a status with a written reason, the criterion it refers to, and its evidence basis (abstract or full text). Never a bare yes/no field.
- Record the source and licence of every full text processed: open access with licence type, or manually provided. Only auto-fetch open access full text with a commercial-use licence (CC0, CC BY, CC BY-SA, CC BY-ND), via the approved PMC routes (BioC API, E-utilities, OAI-PMH, FTP, PMC AWS dataset) or Unpaywall. Skip non-commercial licences and bronze open access.
- Prefer recall over precision in all screening. When uncertain, mark "unclear", never "likely ineligible".
- Primary study full texts are used only for internal eligibility screening. No content from a primary study full text may appear in any guide: no quotes, no extracted data, no paraphrased findings. Guides may reference primary studies by bibliographic details only. Full-text screening reasons and supporting quotes are stored internally and shown only in the internal testing report. Enforce this in code: the guide generator must not have access to primary study full-text content.

## Candidate sources, in priority order

1. Systematic reviews due an update (Step 4A). This is the primary source and should produce most candidates.
2. Gaps stated by review authors (Step 4B). Expect few. A run with no gap candidates is normal, not a failure.
3. Guideline evidence gaps (Step 4C).
4. Completed trials on clinical trial registries (Step 4D).

Every candidate, whatever its source, must be built on primary studies. A guideline or registry entry can justify a question, but the candidate's eligible study count must come from published primary studies.

## Overview of the new flow

1. Topic input: specialty plus topic from the proforma, mapped to MeSH using the existing Stage 0.
2. Discovery: find all systematic reviews, meta-analyses, literature reviews and guidelines in the topic.
3. Checkpoint 1: obtain full texts of the relevant reviews and guidelines (automatic where licensed open access exists, otherwise one manual batch).
4. Candidate mining from the four sources above.
5. Adversarial novelty verification, including PROSPERO and OSF overlap judgements. Confident duplicates are rejected here, before any further work.
6. Search and full title/abstract screening of every hit for each surviving candidate.
7. Rank candidates and shortlist the top 3.
8. Checkpoint 2: one consolidated, deduplicated request for the primary study full texts needed across all 3 shortlisted candidates.
9. Full-text screening, giving confirmed eligible counts.
10. Testing mode: write the evaluation report. Later: human selects a title, and the guide is generated.

## Step 2: Discovery

- Search PubMed and Europe PMC within the topic for systematic review[pt], meta-analysis[pt] and review[pt], plus the Cochrane Database of Systematic Reviews.
- Also search for guideline[pt] and practice guideline[pt] within the topic.
- For each review, record: citation, PMID, DOI, publication year, review type, search end date and number of included studies where stated in the abstract, and open access status with licence.
- For each guideline, record: citation, issuing body where stated, publication year, PMID, DOI, open access status with licence.
- Cap reviews at a configurable number (default 60) and guidelines at a configurable number (default 10), ranked by relevance to the topic.
- The full lists appear in the report so we can see everything the pipeline considered.

## Step 3: Checkpoint 1 (review and guideline full texts)

- Auto-fetch licensed open access full text first.
- Request manual full text only for:
  (a) systematic reviews whose search end date is at least 3 years ago AND which show a preliminary update signal at abstract level (see Step 4A, abstract-level pass),
  (b) reviews published within the last 5 years, for gap extraction, capped at a configurable number (default 15),
  (c) guidelines, for evidence gap extraction, capped at a configurable number (default 5).
- Output one request list for the whole topic: title, year, DOI, PMID, DOI link, link resolver link if configured, reason requested (update candidate, gap extraction, guideline, or a combination).
- The pipeline pauses with status awaiting_review_fulltexts. Provided PDFs go in a run-specific folder, named by PMID or a DOI-safe filename. A resume command matches files automatically (by PMID, DOI, then fuzzy title) and lists anything unmatched or missing. Missing documents are skipped, not guessed.

## Step 4A: Systematic reviews due an update (primary source)

- Abstract-level pass (before checkpoint 1): for systematic reviews whose search end date is at least 3 years ago, extract PICO and search date from the abstract, build a search, and count title/abstract hits published since the search end date. Flag reviews with a promising signal for full text.
- Full-text pass (after checkpoint 1): extract from the full text the PICO, the full inclusion and exclusion criteria, the search end date, the number of included studies, and the list of included studies with identifiers.
- Search for primary studies matching the original PICO published after the original search end date. Screen every hit against the original criteria (Step 6).
- A review becomes an update candidate when the number of possible eligible new studies is at least UPDATE_MIN_NEW (default 5) AND at least UPDATE_MIN_RATIO (default 0.5) times the original number of included studies. Example: original 9 trials, 14 possible new trials qualifies.
- Each update candidate records: original review citation, original search end date, original included count, new possible eligible count, and the list of candidate new papers.
- Run the recall test (below) on every update candidate.

## Step 4B: Gaps stated by review authors (secondary source)

- From each review full text, extract every statement of a gap, typically in the discussion, limitations, conclusions, or "implications for research" sections.
- Each extracted gap must include the verbatim quote, the section it came from, and the PICO elements it implies. No paraphrased gap without its quote.
- Classify each gap:
  - Answerable by a review now: enough relevant primary literature may exist.
  - Needs primary research: for example "more RCTs are needed". Keep these only if a search shows enough relevant primary studies have been published since the review to support a new review. Otherwise discard and record why.
- Frame each surviving gap as a candidate review question in PICO form, with a rationale citing the quoted gap.
- Draft inclusion and exclusion criteria for each gap-based candidate, since there is no original review to inherit them from.

## Step 4C: Guideline evidence gaps

- From each guideline full text, extract recommendations that the guideline itself grades as based on low or very low certainty evidence, or where it states the evidence is insufficient. Each extraction must include the verbatim recommendation text, its stated evidence grade or certainty, and its section.
- For each, identify the primary studies the guideline cites as the evidence for that recommendation, resolved to PMIDs or DOIs.
- Search for primary studies on the same question published after the guideline's evidence search date (or publication date if no search date is stated).
- Frame a candidate review question in PICO form. Its eligible study pool is the cited primary studies plus the newer ones, screened in Step 6. The guideline is the rationale, never a source of eligible studies.
- Draft inclusion and exclusion criteria for each guideline-based candidate.

## Step 4D: Completed trials on registries

- Search ClinicalTrials.gov within the topic for trials with status completed, completed in the last 5 years.
- For each trial, find its published results paper using the NCT number (PubMed secondary source ID field, and Europe PMC full text search for the NCT number).
- Group trials by question. A group becomes a candidate only if no existing review covers it (checked in Step 5) and the number of trials with a published results paper meets MIN_ELIGIBLE.
- The candidate's eligible studies are the published papers only. Registry entries with results but no publication are listed separately in the report and are not counted.
- Draft inclusion and exclusion criteria for each registry-based candidate.

## Step 5: Adversarial novelty verification

Generation is optimistic; this step tries to prove each candidate is already answered.

- Published reviews: search with at least 5 reformulations of each candidate (synonyms, broader and narrower PICO framings) for systematic reviews and meta-analyses published after the source review, guideline or trial completion. For update candidates, also find reviews citing the original review, using the Europe PMC citations endpoint. Any later review citing the original is a likely existing update and must be checked.
- Registries: check the PROSPERO mirror (existing) and the OSF mirror (new, below).
- Overlap judgement, two stages:
  1. Retrieval: find the most similar 30 records per candidate across published reviews and both mirrors, using full text search plus semantic similarity from an embedding model (a local open-source embedding model is fine, to avoid extra cost).
  2. Judgement: a strong reasoning model compares the candidate PICO against each retrieved record and returns structured output: overlap level (duplicate, substantial overlap, partial overlap, none), confidence (high, medium, low), and reasoning referring to population, intervention, comparator, outcomes and study designs. Titles can be worded very differently, so judge on meaning, not wording.
- Reject any candidate judged a duplicate with high confidence, before screening or any full-text request. Show the matching record, its link and the reasoning in the report.
- Substantial overlap with medium confidence: keep, flag prominently in the report.
- Partial overlap: keep, note in the report.

## OSF mirror (new)

- Source: the public OSF API v2 registrations endpoint. No key needed for public reads. Respect rate limits; add a free personal access token later if limits are hit.
- Keep only registrations relevant to systematic reviews in health. Inspect the available registration schemas and select the systematic review templates, plus a keyword and subject filter for health and medicine. Document the filter choices.
- Full harvest once at setup, then a delta pull by registration date before each run, the same pattern as the PROSPERO mirror.
- Store id, title, description, registration schema, date registered, link, and normalised text for matching.
- Apply the same staleness guard as PROSPERO: refuse to run if either mirror is older than the configured threshold (default 10 days).
- Put OSF access behind its own adapter, like PROSPERO.

## Step 6: Search and full title/abstract screening

- For each surviving candidate, screen every hit's title and abstract against the candidate's criteria. No sampling.
- Per record output: status (likely eligible, likely ineligible, unclear), reason referencing the specific criterion, evidence basis.
- Possible eligible count = likely eligible + unclear.
- Early rejection: if the possible eligible count is below MIN_ELIGIBLE (default 8), reject the candidate and record why. No full texts are requested for it.
- If a search returns more than MAX_HITS (default 3000), flag the strategy as too broad rather than screening it.

## Step 7: Rank and shortlist

Score surviving candidates with configurable weights:
- source type, with update candidates given a configurable priority boost, since they are the primary source,
- possible eligible count in the workable range (default 12 to 40),
- strength of update justification (new to original ratio), for updates,
- recency of the evidence base,
- clinical usefulness and novelty as a journal would see it (model judgement, same criteria as the existing tie break: clinical usefulness first, then one-sentence novelty, breadth, clarity, fit with user),
- fit with the user's stated specialty and capacity,
- distance from the nearest registry or published overlap,
- full-text burden (fewer required full texts scores higher).

Shortlist the top SHORTLIST_SIZE (default 3).

## Step 8: Checkpoint 2 (primary study full texts)

- One consolidated, deduplicated request covering all shortlisted candidates. A paper needed by two candidates is requested once.
- Exclude papers already available as licensed open access, which are fetched automatically.
- For each paper: title, year, DOI, PMID, links, which candidates it serves, its title/abstract status and reason.
- Report the number of unique full texts required in total and per candidate.
- Pause with status awaiting_primary_fulltexts. Same upload, matching and resume mechanics as checkpoint 1. Papers still missing at resume stay "unclear, full text unavailable".

## Step 9: Full-text screening

- Screen each full text against the candidate's criteria. Output status, reason with a supporting quote from the paper, and evidence basis. These are internal records only (see the primary study content rule).
- Confirmed eligible count per candidate.
- A candidate passes if confirmed eligible count is at least MIN_ELIGIBLE.
- If none of the shortlisted candidates pass, shortlist the next 3 and repeat checkpoint 2. This should be the exception.

## Recall test protocol (search and screening validation)

Run for every update candidate, using the original review's included studies as the known set.

1. Take the original review's list of included studies and resolve each to a PMID or DOI. Report any that cannot be resolved, or are not indexed in PubMed or Europe PMC, separately; they are excluded from the denominator.
2. Run the candidate's search restricted to the original review's search period.
3. Search recall = known included studies retrieved / known included studies resolvable. Default pass threshold 0.90.
4. Screening recall = known included studies marked likely eligible or unclear at title/abstract stage / known included studies retrieved. Default pass threshold 0.95.
5. For every missed study, report its title and a diagnosis of why it was missed (which search concept or which criterion excluded it).
6. A candidate failing either threshold is flagged and its search strategy revised before any full texts are requested. Record each revision.

For guideline-based candidates, run the same test using the primary studies the guideline cites as the known set. For gap-based candidates, run it if the gap statement cites specific primary studies. For registry-based candidates, use the published results papers. Otherwise report "not applicable".

## Testing-phase report

Produce one report per run, as Markdown plus JSON, containing:

1. Topic and the full lists of reviews and guidelines considered (Step 2).
2. Proposed shortlist: each title in PICO form with its source type and rationale. For update candidates include the original review, its search end date, original included count and new possible count. For gap candidates include the quoted gap and source review. For guideline candidates include the quoted recommendation, its evidence grade and the guideline. For registry candidates include the NCT numbers and their published papers.
3. Possible eligible paper count per title (title/abstract stage) and, after checkpoint 2, confirmed eligible count.
4. Number of full texts required: checkpoint 1 total, and checkpoint 2 unique total plus per candidate.
5. Recall test results per candidate where applicable: search recall, screening recall, missed studies with diagnoses.
6. Registry and published-review overlap per candidate: closest matches from PROSPERO, OSF and published reviews, with overlap level, confidence, reasoning and links.
7. Rejected candidates and the reason for each (duplicate, too few studies, needs primary research, too broad, registry results unpublished), so we can audit rejections.
8. Candidate counts by source type, so we can see how much each source contributes.
9. Model and token usage per stage, and cost per run.

## Backtesting protocol

Purpose: check whether the pipeline proposes real gaps, ones that someone later filled and published.

1. Build a test set of 20 to 30 systematic reviews published in 2026 that were registered on PROSPERO or OSF, roughly half of them updates of earlier reviews. Prefer the most recent ones, to reduce the chance the language model already knows them from training. Store the set with each review's registration date.
2. For each, set a cutoff date of the day before registration.
3. Run the pipeline on the review's specialty and broad topic, not on its specific question. Restrict all literature searches, citation lookups, guideline and trial registry searches, and both registry mirrors to records dated before the cutoff, and exclude the target review explicitly.
4. Instruct every model call in backtest mode to use only provided data, not outside knowledge.
5. Metrics:
   - Hit at 3 and hit at 10: was the target review's question in the shortlist or top 10? Judge the match with the overlap judge (same, overlapping, different), with the reasoning saved for human spot-checking.
   - Update detection: for target updates, did the pipeline flag the original review as due for update before the cutoff, and with what counts?
   - False novelty rate: for each shortlisted candidate, did a duplicate already exist before the cutoff (published or registered)? Any such case is a novelty-check failure; list them.
   - Hits broken down by source type.
6. Output a backtest summary table and per-review details. Results should be reproducible from stored inputs.

Separately, evaluate the overlap judge on a small labelled set of known duplicate and non-duplicate registration pairs. Report precision and recall for the "duplicate, high confidence" decision, since that decision rejects candidates outright.

## Models and reasoning effort

All models configurable. Defaults:

| Task | Model | Reasoning effort |
|---|---|---|
| Discovery, counts, NCT matching | none (APIs only) | n/a |
| Extracting PICO, criteria, search date, included studies from review full text | Sonnet 5.5 | low (grounded extraction) |
| Extracting author-stated gaps with quotes | Sonnet 5.5 | low to medium |
| Extracting graded recommendations and cited studies from guidelines | Sonnet 5.5 | low (grounded extraction) |
| Grouping registry trials by question | Sonnet 5.5 | medium |
| Framing candidates as PICO questions; drafting criteria | Sonnet 5.5 | high |
| Search strategy construction | Sonnet 5.5 | medium |
| Title/abstract screening of all hits | Sonnet 5.5 | medium to high |
| Full-text screening | Sonnet 5.5 | high |
| Overlap judgement (registries, published reviews) | Opus 5.5 | high |
| Clinical usefulness and novelty scoring in ranking | Opus 5.5 | high |
| Backtest match judging | Opus 5.5 | high |
| Simple attribute extraction, fuzzy file and title matching | Haiku 5.5 | none |

Model IDs: claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5. Use structured JSON output with schema validation for every model call. Use the Batch API and prompt caching wherever the call is not interactive (criteria and instructions are identical across every screened record, so cache them).

## Configuration defaults

UPDATE_MIN_AGE_YEARS 3 (measured from search end date), UPDATE_MIN_NEW 5, UPDATE_MIN_RATIO 0.5, MIN_ELIGIBLE 8, WORKABLE_RANGE 12 to 40, MAX_HITS 3000, REVIEW_CAP 60, GUIDELINE_CAP 10, GAP_REVIEW_CAP 15, GAP_REVIEW_MAX_AGE_YEARS 5, GUIDELINE_FULLTEXT_CAP 5, TRIAL_COMPLETION_MAX_AGE_YEARS 5, SHORTLIST_SIZE 3, OVERLAP_RETRIEVAL_K 30, SEARCH_RECALL_MIN 0.90, SCREEN_RECALL_MIN 0.95, MIRROR_STALENESS_DAYS 10, ENABLE_GAP_SOURCE true, ENABLE_GUIDELINE_SOURCE true, ENABLE_REGISTRY_SOURCE true, UPDATE_PRIORITY_BOOST configurable.

## Data to store

Add tables (or equivalents in the existing schema) for: reviews, guidelines, trials (with NCT number and linked publication), fulltexts (with source, licence, provenance, and a flag marking primary study full texts as internal-only), gap_statements (with verbatim quote and section), guideline_recommendations (with verbatim text, evidence grade, cited studies), candidates (source type, PICO, criteria, status, rejection reason, verification date), screening_records, fulltext_requests, osf_mirror, overlap_judgements, recall_tests, runs, backtest_cases, backtest_results.

Store every candidate permanently with its status and verification date, including rejected ones. This is the foundation for a later question bank, where verified candidates are reused for future requests and re-verified on the day of delivery. Do not build the serving side of the bank yet.

## Deferred, do not build now

- Question bank serving.
- WHO ICTRP and other trial registries beyond ClinicalTrials.gov.
- Guide generation changes. Guide generation stays disabled in testing mode.

## Milestones and acceptance tests

1. OSF mirror and overlap judge. Test: mirror harvests and delta pulls correctly; overlap judge evaluated on the labelled pair set.
2. Discovery and checkpoint 1. Test: run on a topic, review and guideline lists are complete and correct; open access fetch respects licence rules; manual upload, matching and resume work, including missing files.
3. Update mining and recall test. Test: on 3 known Cochrane reviews with later published updates, the pipeline flags them as due and the recall test reports correct numbers.
4. Gap mining. Test: every extracted gap has a verbatim quote that appears in the source text; "needs primary research" gaps are classified and handled correctly.
5. Guideline and registry sources. Test: every guideline extraction has verbatim text and an evidence grade found in the source; every registry candidate counts only trials with a linked published paper; guidelines and registry entries are never counted as eligible studies.
6. Novelty verification. Test: a deliberately duplicated candidate is rejected with high confidence before any full-text request; a genuinely novel one is not.
7. Full screening, ranking, checkpoint 2 and full-text screening. Test: every hit is screened (no sampling); the consolidated request is deduplicated; the same record screened twice gives consistent status and reasoning; no primary study full-text content is reachable from the guide generator.
8. Testing report. Test: all 9 report sections present for a full run.
9. Backtest harness. Test: date restrictions are enforced (no record after the cutoff appears anywhere in the run); summary metrics compute correctly.