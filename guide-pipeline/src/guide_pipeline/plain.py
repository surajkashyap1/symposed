"""Plain English for first-time researchers.

Two jobs:
  * `tidy` cleans model-written prose to the house style: no semicolons and no
    em or en dashes (Suraj, 2026-10-17). Hyphenated words such as
    "meta-analysis" keep their hyphen. Search syntax is never passed through
    here, because semicolons and dashes can be meaningful in a query.
  * `glossary_for` picks the glossary entries a guide actually needs: every
    term below that appears anywhere in the guide's text, plus the project
    specific terms the model defined for this question.
"""

from __future__ import annotations

import re
from typing import Iterable

_SPACED_DASH = re.compile(r"\s+[—–-]{1,2}\s+")  # " - ", " — ", " -- "
_TIGHT_DASH = re.compile(r"(?<=\w)[—–](?=\w)")  # word—word, 2015–2020
_SEMI = re.compile(r"\s*;\s*(\S)")


def tidy(text: str) -> str:
    """House style for prose: no semicolons, no em or en dashes."""
    if not text:
        return text
    t = _SPACED_DASH.sub(", ", text)
    t = re.sub(r"(\d)[–—](\d)", r"\1 to \2", t)  # ranges read as "to"
    t = re.sub(r"(?<=\w)\u2013(?=\w)", "-", t)  # pre–post reads as pre-post
    t = _TIGHT_DASH.sub(", ", t)
    t = t.replace("—", ", ").replace("–", ", ")
    t = _SEMI.sub(lambda m: ". " + m.group(1).upper(), t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def tidy_all(items: Iterable[str]) -> list[str]:
    return [tidy(str(x)) for x in items]


# Terms a beginner meets in a review guide. Keys are the display form; the
# match uses the lower-cased key plus any aliases.
GLOSSARY: dict[str, tuple[str, tuple[str, ...]]] = {
    "Abstract": ("The short summary at the start of a paper. Screening usually starts with "
                 "the title and abstract only.", ()),
    "AMSTAR 2": ("A checklist for judging how well a systematic review was carried out. It is "
                 "used when the papers you review are themselves reviews.", ()),
    "Bias": ("Anything in the way a study was designed or run that could push its results "
             "away from the truth.", ("risk of bias",)),
    "Boolean operators": ("The words AND, OR and NOT used to combine search terms. OR widens "
                          "a search (either word), AND narrows it (both words).",
                          ("boolean",)),
    "CHARMS": ("A checklist that tells you which details to extract from studies that build or "
               "test prediction models.", ()),
    "Cochrane Library": ("A collection of databases of trials and high quality reviews. "
                         "CENTRAL is its database of trials.", ("cochrane central", "central")),
    "Comparator": ("What the treatment or exposure is compared against, for example a placebo "
                   "or the usual treatment. The C in PICO.", ()),
    "Confidence interval": ("The range in which the true result probably lies. A narrow range "
                            "means a more precise result.", ("95% ci",)),
    "Covidence": ("A paid online tool for screening papers and extracting data. Many "
                  "universities subscribe.", ()),
    "Data extraction": ("Copying the same set of details (such as sample size and results) "
                        "out of every included paper into one table.", ()),
    "Database": ("A searchable collection of published papers, such as PubMed or Embase.",
                 ("databases",)),
    "DOI": ("Digital Object Identifier. A permanent link to a paper. Put https://doi.org/ in "
            "front of it to open the paper.", ()),
    "Duplicate": ("The same paper found in more than one database. Duplicates are removed "
                  "before screening.", ("duplicates",)),
    "Embase": ("A large database of medical and drug research, run by Elsevier. Usually "
               "available through a university or NHS library.", ()),
    "Exclusion criteria": ("The rules that rule a paper out of your review.", ()),
    "Forest plot": ("A chart that shows the result of each study as a line and the combined "
                    "result as a diamond.", ()),
    "Full text": ("The complete paper, not just its abstract.", ("full texts",)),
    "GRADE": ("A method for rating how confident you can be in a body of evidence (high, "
              "moderate, low or very low).", ()),
    "Grey literature": ("Research that is not published in journals, such as conference "
                        "abstracts, theses, reports and trial registries.", ()),
    "Heterogeneity": ("How much the studies differ from each other in who they studied, what "
                      "they did or what they found.", ()),
    "Inclusion criteria": ("The rules a paper must meet to be part of your review.",
                           ("eligibility criteria", "eligibility")),
    "Intervention": ("The treatment, test or exposure being studied. The I in PICO.",
                     ("exposure",)),
    "Literature review": ("A review that summarises what is known on a topic using a clear but "
                          "less strict method than a systematic review.", ()),
    "MeSH": ("Medical Subject Headings. PubMed's own list of standard topic labels. Searching "
             "with a MeSH term finds papers on that topic even when they use different "
             "words.", ("mesh terms", "[mesh]")),
    "Meta-analysis": ("A statistical method that combines the numerical results of several "
                      "studies into one overall result.", ()),
    "Narrative review": ("A review that discusses a topic in an expert, descriptive way rather "
                         "than following a strict search and screening method.", ()),
    "Newcastle-Ottawa Scale": ("A star based checklist for judging the quality of cohort and "
                               "case control studies.", ("newcastle",)),
    "Outcome": ("What is measured to see if something worked, for example survival or pain. "
                "The O in PICO.", ("outcomes",)),
    "PICO": ("A way of breaking a question into Population, Intervention, Comparator and "
             "Outcome. It keeps the question and the search focused.", ()),
    "PMID": ("PubMed's ID number for a paper. Typing it into PubMed takes you straight to "
             "the paper.", ()),
    "Population": ("The group of people the question is about. The P in PICO.", ()),
    "Preprint": ("A paper shared online before it has been peer reviewed.", ("preprints",)),
    "PRISMA": ("The reporting rules for systematic reviews, including the PRISMA flow diagram "
               "that shows how many papers you found, removed and kept.", ("prisma 2020",)),
    "PROBAST": ("A tool for judging the risk of bias in studies that build or test prediction "
                "models.", ()),
    "PROSPERO": ("The free international register of systematic review protocols. Registering "
                 "creates a public, dated record that the question is yours.", ()),
    "Protocol": ("Your written plan for the review, made before you start: the question, "
                 "the search, the inclusion rules and how you will analyse the results. Also "
                 "called a standard operating procedure (SOP).", ("sop",)),
    "PubMed": ("The free search engine for medical research, run by the US National Library "
               "of Medicine.", ()),
    "QUADAS-2": ("A tool for judging the risk of bias in diagnostic accuracy studies.", ()),
    "Randomised controlled trial": ("A study where people are randomly put into groups that "
                                    "get different treatments. Often shortened to RCT.",
                                    ("rct", "randomised", "randomized")),
    "Rayyan": ("A free website for screening papers with your team. Each person marks every "
               "paper include, exclude or maybe without seeing the others' choices.", ()),
    "Reference manager": ("Software that stores your papers and formats your references, "
                          "such as Zotero (free), Mendeley or EndNote.", ("zotero",)),
    "Risk of bias tool": ("A structured checklist for judging how much you can trust each "
                          "study's results.", ()),
    "RIS file": ("A standard file format for exporting a list of papers from a database so "
                 "you can import it into Rayyan or a reference manager.", ("ris",)),
    "RoB 2": ("The Cochrane tool for judging the risk of bias in randomised trials.", ()),
    "ROBINS-I": ("The Cochrane tool for judging the risk of bias in non randomised studies of "
                 "treatments.", ()),
    "ROBIS": ("A tool for judging the risk of bias in systematic reviews.", ()),
    "Screening": ("Going through the papers your search found and deciding which ones meet "
                  "your inclusion criteria. First by title and abstract, then by full text.",
                  ("screen",)),
    "Search strategy": ("The exact combination of search terms and Boolean operators you type "
                        "into a database.", ("search strategies",)),
    "Synthesis": ("Bringing the findings of the included studies together, with numbers "
                  "(meta-analysis) or in words (narrative synthesis).", ("synthesise",)),
    "Systematic review": ("A review that answers a focused question by searching for, "
                          "selecting and appraising every relevant study using a strict, "
                          "pre planned method.", ()),
    "Title and abstract screening": ("The first round of screening, where you decide on each "
                                     "paper from its title and abstract alone.", ()),
    "Truncation": ("Adding * to the end of a word so the search finds every ending, for "
                   "example child* finds child, children and childhood.", ("wildcard",)),
}


def glossary_for(text: str, extra: Iterable[dict] = ()) -> list[dict[str, str]]:
    """Glossary entries whose term appears in `text`, plus project terms, A to Z."""
    low = text.lower()
    out: dict[str, str] = {}
    for term, (definition, aliases) in GLOSSARY.items():
        if any(_mentions(low, w) for w in (term.lower(), *aliases)):
            out[term] = definition
    for item in extra:
        term = tidy(str(item.get("term", ""))).strip()
        definition = tidy(str(item.get("definition", ""))).strip()
        if term and definition and term.lower() not in {k.lower() for k in out}:
            out[term] = definition
    return [{"term": k, "definition": out[k]} for k in sorted(out, key=str.lower)]


def _mentions(low_text: str, word: str) -> bool:
    if not word.isalnum() and not word.replace(" ", "").replace("-", "").isalnum():
        return word in low_text
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", low_text) is not None
