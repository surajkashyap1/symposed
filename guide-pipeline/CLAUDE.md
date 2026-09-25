# Guide pipeline — session rules

Standalone Python tool (run by hand) that drafts one Publication Guide from one
proforma. Separate from the Symposed Next.js app in the parent repo. Build
**ONE STEP PER SESSION**, write tests, run them, only advance when green. See
`README.md` for the step plan.

## Two rules that never bend

1. Every citation, PMID, DOI, title and count MUST come from an API response
   (PubMed / Europe PMC / ClinicalTrials.gov). The model NEVER supplies any of
   these from its own knowledge.
2. There is NO include/exclude field anywhere. The pipeline suggests papers and
   says why. The user decides what goes in their review.

## Conventions
- Gate thresholds and limits are **settings** (env / `Thresholds`), never hardcoded.
- Cache every external API response; respect rate limits (PubMed 10 req/s with a key).
- LLM calls use structured JSON output the code validates. **Groq first**
  (`LLM_PROVIDER=groq`); switchable to Claude (`anthropic`) with no code change.
- PROSPERO access goes ONLY through `prospero/adapter.py` (undocumented endpoint,
  may be replaced by a CRD feed). The pipeline queries the local mirror, never
  PROSPERO per title. Checks refuse to run on a stale mirror — never bypass that.
- A human reviews every output and does a final live PROSPERO check on the title
  that ships. Never fully automate generation and delivery.
