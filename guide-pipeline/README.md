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
- **Step 3 — Candidates & gates**: LLM makes 8–12 candidate titles across distinct
  axes; count-only queries; apply gates; rank survivors. ✅
  (`python -m guide_pipeline candidates "<topic>"`)
- **Step 4 — Deep retrieval**: chosen title only — full records + abstracts,
  dedupe (DOI → PMID → title+year), tag each paper with a suggested use. ✅
  (`python -m guide_pipeline retrieve "<pubmed query>"`)
- **Step 5 — The guide**: draft the Word doc from retrieved records only (§6 of
  the pipeline spec), including the date the searches were run.

Models (spec): Claude Sonnet 5 for titles + drafting, Claude Haiku 4.5 for
tagging. We are trialling **Groq's free model first** and will switch to Claude if
quality is too low — the LLM layer is provider-agnostic.

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
- **Groq API key** (free tier): https://console.groq.com/keys
- **Anthropic API key** (later, if switching to Claude): https://console.anthropic.com/

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
```

## Test

```bash
pytest
```
