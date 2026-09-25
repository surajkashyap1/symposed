# Spec update (Samarth, received 2026-09-25): full-recall screening replaces tagging

Update to the pipeline spec, replacing the tagging step in Stage 5.

## What's changing

The original spec had the pipeline label each paper with a suggested use category
(background, methods justification, potential included study, etc) with no
eligibility judgement at all. We're upgrading this. The pipeline should now run a
full, rigorous screen of every retrieved paper against the review's own inclusion
and exclusion criteria, aiming for as close to complete recall as possible, same
intent as a real reviewer doing title and abstract screening.

The output is still not a decision. It's a graded, reasoned recommendation that
the user reads and checks. Never a hidden yes/no flag.

## Why this distinction matters and must be built exactly this way

We cannot claim to have screened the papers for the user, for two reasons:
authorship rules (we're not doing the review, they are) and research integrity (an
AI making silent inclusion decisions on a review that might inform clinical
guidelines is not acceptable). The disclaimer in every guide states plainly that
the papers are suggestions, not screened, and that the user makes their own
decisions.

The line that keeps this true: the pipeline can and should aim for full recall
internally, but every output has to show its reasoning, not just a verdict, and
has to be visibly framed as an estimate the user must verify. A silent boolean
field is not allowed anywhere in the schema, same as before. A visible field with a
graded status and a written reason is fine and is what we're building now.

## The new per-paper output

For every retrieved paper, produce:
- **Status**: one of "likely eligible", "likely ineligible", or "unclear, check full text"
- **Reason**: a sentence stating why, referencing the specific criterion, e.g.
  "Matches population and intervention. Outcome not stated in the abstract."
- **Evidence basis**: whether the assessment was made from the abstract only, or
  from full text

This replaces the old suggested-use taxonomy. Keep the structured attribute
extraction (design, population, sample size, intervention, comparator, outcomes,
country, year) as its own step feeding into this one, since the screening
reasoning depends on having those pulled out first.

## Full text, where it's actually available

We are not getting full text from Embase, Scopus or any publisher API, and we are
not using anyone's institutional login in the pipeline, for licensing and
access-agreement reasons that aren't going away. What we can do for free:

- Pull full text from Europe PMC for the open access subset.
- Run the screening reasoning against full text wherever it's available, and mark
  the evidence basis field accordingly.
- For everything else, screen from the abstract only, and mark that clearly.
  Never infer a full-text-only detail from an abstract.
- For papers marked "unclear, check full text" with no open access version,
  generate a formatted list by DOI that the user can pull through their own
  institutional access. Don't try to automate fetching those.

## New test: recall, not just accuracy

Take three or four real published systematic reviews we already know the answer
for. Feed their research question and criteria into the pipeline, run the
screening step against the same literature set, and check what proportion of the
papers that review actually included get marked "likely eligible" or "unclear" by
our pipeline, rather than "likely ineligible". We're aiming for high recall:
missing a paper that should have been flagged is a much worse failure than over
including one that gets filtered out later. Track this number across test runs.

## One more acceptance check

Run the same paper through the screening step twice with the same criteria. The
status and reasoning should be consistent. If it flips between eligible and
ineligible on identical input, effort or prompting needs adjusting before this
ships to a real customer.

## Model and reasoning effort by task

Effort scales with how much of the output is created versus transformed versus
extracted: high where the model does design work with no source to check against,
low or none where it should stick closely to what's written down.

| Task | Model | Reasoning effort | Notes |
|---|---|---|---|
| Concept mapping (Stage 0) | GPT-6 Luna or Haiku 4.5 | None | Structured extraction, then MeSH lookup |
| Candidate generation (Stage 2) | Sonnet 5 or GPT-6 Sol | High | Open ended, needs to range across the 14 axes |
| Search strategy construction | Sonnet 5 or GPT-6 Sol | Medium | Real syntax accuracy; too much reasoning invents MeSH terms |
| Attribute extraction | GPT-6 Luna or Haiku 4.5 | None | Reading stated facts out of text, not judgement |
| Full recall screening (replaces tagging) | Sonnet 5 or GPT-6 Sol | Medium to high | Real reasoning against explicit criteria |
| Writing inclusion and exclusion criteria | Sonnet 5 or GPT-6 Sol | High | Genuine design work |
| Protocol and SOP drafting | Sonnet 5 or GPT-6 Sol | Medium to high | Partly constrained by criteria already written |
| PROSPERO form | Sonnet 5, cheaper tier acceptable | Low | Reformatting the finished protocol |
| Guide assembly and final drafting | Sonnet 5 or GPT-6 Sol | Low or none | Must stay grounded in retrieved records |
| Tie break (Stage 5b) | Opus 5.5 or GPT-6 Astra | Max | Rare, genuine judgement call |

GPT-6 Luna ($0.10/$0.50 per million tokens) and Claude Haiku 4.5 are both fine for
the None-effort rows. For the Sonnet-or-Sol rows, compare both on the same test
topics once this is working rather than committing to one now.
