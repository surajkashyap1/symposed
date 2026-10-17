"""The render model: everything the PDF guide and its companion files show.

`build_model` turns a `GuideContent` (live objects) into one plain, JSON-ready
dict. It is saved as `guide_model.json` beside the outputs so a guide can be
re-rendered after a design change without any model calls (`render` command).

Step names live in `steps()` and nowhere else. The overview, the timeline, the
banners, the contents page and every cross reference read them from here, so a
step is always called the same thing (Suraj, 2026-10-17).
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

from .plain import glossary_for, tidy, tidy_all
from .rob_tools import choose_tools
from .screening import LIKELY_ELIGIBLE, NOT_STATED, UNCLEAR

# -- steps --------------------------------------------------------------------------
_SR_STEPS = (
    ("check", "Check your question is new",
     "Search PROSPERO and PubMed again, and show the question to a supervisor."),
    ("protocol", "Write and register your protocol",
     "Edit the draft protocol, then register it on PROSPERO."),
    ("search", "Search the databases",
     "Run the search strategy in each database and export the results."),
    ("screen", "Screen the papers",
     "Two of you decide independently which papers meet the rules."),
    ("extract", "Extract the data",
     "Copy the same details from every included paper into the tracker."),
    ("bias", "Assess the risk of bias",
     "Judge how far each included study can be trusted."),
    ("analyse", "Analyse and combine the results",
     "Bring the results together, with numbers or in words."),
    ("write", "Write your review",
     "Write it up using the PRISMA structure and figures."),
    ("submit", "Submit to a journal",
     "Choose a journal, add the declarations and submit."),
)
_LIT_STEPS = (
    ("check", "Check your question is new",
     "Search PubMed again for recent reviews, and show the question to a supervisor."),
    ("protocol", "Write your protocol",
     "Edit the draft protocol so the whole team follows the same plan."),
    ("search", "Search the databases",
     "Run the search strategy and export the results."),
    ("screen", "Screen the papers",
     "Decide which papers meet the rules for your review."),
    ("extract", "Extract the data",
     "Copy the same details from every included paper into the tracker."),
    ("bias", "Appraise the quality of the studies",
     "Judge the strengths and weaknesses of the key studies."),
    ("analyse", "Combine the findings",
     "Group the findings into themes and compare them."),
    ("write", "Write your review",
     "Write it up with a clear structure and summary table."),
    ("submit", "Submit to a journal",
     "Choose a journal, add the declarations and submit."),
)

# Timeline hours per step, per person, beyond the screening and extraction
# workload (which is computed from the numbers).
_FIXED_HOURS = {"check": 2.0, "protocol_sr": 6.0, "protocol_lit": 3.0, "search": 5.0,
                "analyse_sr": 15.0, "analyse_lit": 10.0, "write": 20.0, "submit": 5.0}
HOURS_PER_WEEK = {"Under 3": 2.0, "3 to 5": 4.0, "5 to 10": 7.5, "Over 10": 12.0}


def steps(systematic: bool) -> list[dict[str, Any]]:
    rows = _SR_STEPS if systematic else _LIT_STEPS
    return [{"number": i, "key": k, "name": n, "summary": s}
            for i, (k, n, s) in enumerate(rows, 1)]


def step_timeline(*, systematic: bool, records: int, eligible: int, team: int,
                  hours_label: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hours and weeks per step, from the user's hours and the screening volume."""
    per_week = HOURS_PER_WEEK.get(hours_label, 4.0)
    team = max(team, 2)
    sr = systematic
    hours = {
        "check": _FIXED_HOURS["check"],
        "protocol": _FIXED_HOURS["protocol_sr" if sr else "protocol_lit"],
        "search": _FIXED_HOURS["search"],
        # each record seen by two people: 1 min per abstract, 15 per full text
        "screen": records * 1.0 * 2 / team / 60 + eligible * 15.0 * 2 / team / 60,
        "extract": eligible * 30.0 / team / 60,
        "bias": eligible * 20.0 * (2 if sr else 1) / team / 60,
        "analyse": _FIXED_HOURS["analyse_sr" if sr else "analyse_lit"],
        "write": _FIXED_HOURS["write"],
        "submit": _FIXED_HOURS["submit"],
    }
    out, total = [], 0.0
    for st in steps(sr):
        h = max(round(hours[st["key"]], 1), 0.5)
        start = int(total // per_week) + 1
        total += h
        end = max(start, math.ceil(total / per_week - 1e-9))
        out.append({**st, "hours": h, "start_week": start, "end_week": end})
    assumptions = {
        "hours_per_week_each": per_week, "team": team, "records_to_screen": records,
        "eligible_estimate": eligible, "total_weeks": out[-1]["end_week"] if out else 0,
        "total_hours": round(total, 1),
    }
    return out, assumptions


# -- papers ---------------------------------------------------------------------------
# PubMed types that say nothing about the design.
_GENERIC_TYPES = {
    "journal article", "english abstract", "comment", "letter", "editorial", "news",
    "published erratum", "research support, non-u.s. gov't", "research support, u.s. gov't",
    "research support, n.i.h., extramural", "research support, n.i.h., intramural",
    "research support, u.s. gov't, non-p.h.s.", "research support, u.s. gov't, p.h.s.",
    "video-audio media", "introductory journal article", "historical article",
}
# Most specific first: the first match names the paper.
_TYPE_ORDER = (
    "Systematic Review", "Meta-Analysis", "Network Meta-Analysis", "Scoping Review",
    "Randomized Controlled Trial", "Pragmatic Clinical Trial", "Controlled Clinical Trial",
    "Clinical Trial, Phase III", "Clinical Trial, Phase II", "Clinical Trial",
    "Observational Study", "Multicenter Study", "Comparative Study", "Validation Study",
    "Evaluation Study", "Case Reports", "Practice Guideline", "Guideline",
    "Consensus Development Conference", "Review", "Clinical Trial Protocol", "Preprint",
)


# PubMed types that say something, but less than a design read from the abstract.
_WEAK_TYPES = {"Comparative Study", "Multicenter Study", "Evaluation Study",
               "Validation Study"}


def likely_publication_type(publication_types: list[str], design_guess: str,
                            *, preprint: bool = False) -> tuple[str, str]:
    """(label, basis). PubMed's own type when it is specific, else our estimate."""
    if preprint:
        return "Preprint (not yet peer reviewed)", "source"
    specific = [t for t in publication_types if t.lower() not in _GENERIC_TYPES]
    strong = [t for t in specific if t not in _WEAK_TYPES]
    for t in _TYPE_ORDER:
        if t in strong:
            return _british(t), "PubMed"
    if strong:
        return _british(strong[0]), "PubMed"
    guess = shorten((design_guess or "").strip(), 45)
    if guess and guess.lower() != NOT_STATED.lower():
        return tidy(guess[0].upper() + guess[1:]), "our estimate"
    if specific:
        return _british(specific[0]), "PubMed"
    return "Not clear from the abstract", "our estimate"


def shorten(text: str, limit: int) -> str:
    """The core of a long extracted phrase: before any bracket, then cut at a word."""
    t = re.split(r"\s*[(\[;]", text, maxsplit=1)[0].strip().rstrip(",.")
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0].rstrip(",.")
    return cut + "\u2026"


def _british(t: str) -> str:
    """PubMed's title case to British sentence case ("Randomized Controlled Trial" ->
    "Randomised controlled trial"), keeping roman numerals such as Phase III."""
    t = t.replace("Randomized", "Randomised").replace("Case Reports", "Case report")
    words = t.split(" ")
    return " ".join([words[0]] + [w if w.isupper() else w.lower() for w in words[1:]])


def paper_rows(screening: Any) -> list[dict[str, Any]]:
    """The papers we suggest reading: likely eligible or unclear, never the rest.

    The guide shows no rating (Suraj, 2026-10-17): every listed paper is one we
    think the user should look at, and what they do with it is their decision.
    """
    rows = []
    for sp in screening.papers:
        if sp.status not in (LIKELY_ELIGIBLE, UNCLEAR):
            continue
        p, a = sp.paper, sp.attributes or {}
        label, basis = likely_publication_type(list(getattr(p, "publication_types", ())),
                                               str(a.get("design", "")),
                                               preprint=p.is_preprint)
        url = (f"https://europepmc.org/article/PPR/{p.pmid}" if p.is_preprint
               else f"https://pubmed.ncbi.nlm.nih.gov/{p.pmid}/")
        rows.append({
            "pmid": p.pmid, "id_label": "Europe PMC" if p.is_preprint else "PMID",
            "doi": p.doi or "", "title": p.title.rstrip("."), "year": p.year,
            "first_published": p.first_published_year, "journal": p.journal,
            "first_author": p.authors[0] if p.authors else "No author listed",
            "authors": list(p.authors), "abstract": p.abstract,
            "publication_type": label, "publication_type_basis": basis,
            "sample_size": shorten(_clean_attr(a.get("sample_size")), 28),
            "population": _clean_attr(a.get("population")),
            "url": url, "full_text_open": bool(sp.open_access_pmcid),
        })
    rows.sort(key=lambda r: (-(r["first_published"] or r["year"] or 0), r["first_author"]))
    for i, r in enumerate(rows, 1):
        r["n"] = i
    return rows


def _clean_attr(v: Any) -> str:
    if v is None:
        return ""
    s = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return "" if s.strip().lower() in ("", NOT_STATED.lower(), "none") else tidy(s)


# -- the whole model ----------------------------------------------------------------
def build_model(content: Any, *, proforma: Optional[dict] = None,
                retrieval_query: str = "", retrieval_count: Optional[int] = None
                ) -> dict[str, Any]:
    c = content
    p = proforma or {}
    systematic = c.systematic
    papers = paper_rows(c.papers)

    # Searches, numbered once and referred to by number everywhere. Search 1 is
    # the one that found the suggested papers.
    s = c.strategies
    searches = []
    if retrieval_query:
        searches.append({"name": "The search that found your suggested papers",
                         "purpose": "This is the search we ran to find the papers listed in "
                                    "step 4. It is a good starting point but deliberately "
                                    "focused, so use one of the fuller strategies below "
                                    "for your own search.",
                         "query": retrieval_query, "count": retrieval_count,
                         "recommended": False, "found_papers": True})
    for i, st in enumerate(s.get("strategies", [])):
        searches.append({"name": tidy(st.name), "purpose": tidy(st.purpose),
                         "query": st.pubmed_query, "count": st.count,
                         "recommended": i == s.get("recommended"), "found_papers": False})
    for i, x in enumerate(searches, 1):
        x["number"] = i
    papers_search = next((x["number"] for x in searches if x["found_papers"]), None)
    recommended = next((x["number"] for x in searches if x["recommended"]), None)

    tools = choose_tools(c.criteria.study_designs, getattr(c, "axis", ""),
                         systematic=systematic)
    timeline, assumptions = step_timeline(
        systematic=systematic,
        records=c.feasibility.get("records_to_screen", 0),
        eligible=len(papers) or c.feasibility.get("eligible_screened", 0),
        team=c.feasibility.get("recommended_team", 2),
        hours_label=str(p.get("hoursPerWeek", "")))

    crit = c.criteria
    model: dict[str, Any] = {
        "version": 2,
        "title": c.title,
        "publication_type": c.publication_type,
        "systematic": systematic,
        "generated_on": c.generated_on,
        "search_date": c.search_date,
        "novelty_date": c.novelty_date,
        "prepared_for": str(p.get("preparedFor") or p.get("fullName") or "").strip(),
        "profile": {
            "grade": p.get("grade", ""), "hours": p.get("hoursPerWeek", ""),
            "team": c.feasibility.get("recommended_team", 2),
            "databases": list(p.get("databases") or []),
            "stats": p.get("statsConfidence", ""), "timeline": p.get("timeline", ""),
            "specialties": list(p.get("specialties") or []),
        },
        "steps": steps(systematic),
        "pico": [[k, tidy(v)] for k, v in c.pico if v],
        "rationale": tidy(c.rationale),
        "references": c.references,
        "similar": [{"title": d["title"], "url": d["url"],
                     "difference": tidy(c.differences.get(i, ""))}
                    for i, d in enumerate(c.similar, 1)],
        "feasibility": c.feasibility,
        "searches": searches,
        "papers_search_number": papers_search,
        "recommended_search_number": recommended,
        "recommendation_reason": tidy(s.get("recommendation_reason", "")),
        "embase": s.get("embase_emtree", ""),
        "cochrane": s.get("cochrane_central", ""),
        "papers": papers,
        "own_access": [{"title": x.paper.title, "doi": x.paper.doi or "",
                        "pmid": x.paper.pmid}
                       for x in c.papers.unclear_without_open_access()],
        "criteria": {
            "population": tidy(crit.population),
            "intervention": tidy(crit.intervention_or_exposure),
            "comparator": tidy(crit.comparator), "outcomes": tidy(crit.outcomes),
            "designs": tidy(crit.study_designs), "setting": tidy(crit.setting),
            "other_inclusion": tidy_all(crit.other_inclusion),
            "exclusion": tidy_all(crit.exclusion),
        },
        "criteria_reasoning": [{"criterion": tidy(r.get("criterion", "")),
                                "reasoning": tidy(r.get("reasoning", ""))}
                               for r in c.criteria_reasoning],
        "decision_tree": [{"question": tidy(q.get("question", "")),
                           "no_label": tidy(q.get("no_label", ""))}
                          for q in getattr(c, "decision_tree", []) if q.get("question")],
        "exclusion_reasons": _exclusion_reasons(getattr(c, "decision_tree", []), crit),
        "prospero": ({k: tidy(v) for k, v in c.prospero.items()} if c.prospero else None),
        "rob_tools": [t.as_dict() for t in tools],
        "reporting": c.reporting,
        "aims": tidy(c.aims),
        "objectives": tidy_all(c.objectives),
        "analysis": tidy(c.analysis),
        "skills": tidy_all(c.skills),
        "extraction_fields": list(c.extraction_fields),
        "prisma": c.prisma,
        "structure": [[h, list(subs)] for h, subs in c.structure],
        "timeline": timeline,
        "timeline_assumptions": assumptions,
        "journals": [[j, n] for j, n in c.journals],
        "search_appendix": c.search_appendix,
        "warnings": list(c.warnings),
        "screenshots": {},
    }
    corpus = " ".join([
        c.rationale, c.analysis, c.aims, " ".join(c.objectives), crit.as_text(),
        " ".join(c.reporting), " ".join(t.name for t in tools), _FIXED_TEXT,
        _FIXED_SR_TEXT if systematic else "",
    ])
    model["glossary"] = glossary_for(corpus, getattr(c, "project_glossary", []))
    return model


def _exclusion_reasons(tree: list[dict], crit: Any) -> list[str]:
    """Dropdown options for 'reason for exclusion' in the tracker."""
    reasons = [tidy(q.get("no_label", "")) for q in tree if q.get("no_label")]
    reasons += [tidy(f"Excluded: {e}") for e in crit.exclusion]
    reasons += ["Duplicate", "Full text not available", "Other (write in notes)"]
    out: list[str] = []
    for r in reasons:
        r = r[:250]
        if r and r not in out:
            out.append(r)
    return out


# Words the fixed guide text always uses, so their glossary entries are kept.
_FIXED_TEXT = (
    "PubMed MeSH Boolean operators truncation PICO protocol screening Rayyan RIS file "
    "title and abstract screening full text data extraction risk of bias tool PMID DOI "
    "reference manager duplicate inclusion criteria exclusion criteria grey literature "
    "search strategy preprint abstract synthesis"
)
_FIXED_SR_TEXT = "PROSPERO PRISMA meta-analysis forest plot"
