# Guide pipeline — session rules

Standalone Python tool (run by hand) that drafts one Publication Guide from one
proforma. Separate from the Symposed Next.js app in the parent repo. Build
**ONE STEP PER SESSION**, write tests, run them, only advance when green. See
`README.md` for the step plan.

## Two rules that never bend

1. Every citation, PMID, DOI, title and count MUST come from an API response
   (PubMed / Europe PMC / ClinicalTrials.gov). The model NEVER supplies any of
   these from its own knowledge.
2. There is NO silent include/exclude field anywhere — no boolean, no hidden
   verdict. Per the screening update (`docs/spec-update-screening.md`) a paper may
   carry a VISIBLE graded status ("likely eligible" / "likely ineligible" /
   "unclear, check full text") with a written reason and its evidence basis
   (abstract or full text), framed as an estimate. The user decides what goes in.

## Conventions
- Gate thresholds and limits are **settings** (env / `Thresholds`), never hardcoded.
- Cache every external API response; respect rate limits (PubMed 10 req/s with a key).
- LLM calls use structured JSON output the code validates. **Claude Sonnet 5 for
  every task**; each call names its task (`build_llm(settings, "<task>")`) so it
  gets that task's effort/thinking from `llm.TASKS`. New task → add it there.
  Live runs cost money: print the `UsageMeter` summary, and keep tests on fakes.
- PROSPERO access goes ONLY through `prospero/adapter.py` (undocumented endpoint,
  may be replaced by a CRD feed). The pipeline queries the local mirror, never
  PROSPERO per title. Checks refuse to run on a stale mirror — never bypass that.
- A human reviews every output and does a final live PROSPERO check on the title
  that ships. Never fully automate generation and delivery.
