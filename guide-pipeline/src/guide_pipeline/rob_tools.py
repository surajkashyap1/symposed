"""Risk of bias and appraisal tools, chosen by the designs a review includes.

Each tool carries what a beginner needs: what it is for, where to get it, its
domains, the judgements it allows and how the domain judgements combine into an
overall judgement. The guide draws the decision tree from these, and the
tracker spreadsheet gets one column per domain with the tool's judgements as a
dropdown. Links are the tools' official homes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    full_name: str
    use_for: str
    link: str
    domains: tuple[str, ...]
    judgements: tuple[str, ...]  # best first
    overall_rule: tuple[str, ...]  # plain sentences, applied in order
    companions: tuple[tuple[str, str, str], ...] = field(default=())  # (name, link, why)

    def as_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "full_name": self.full_name,
            "use_for": self.use_for, "link": self.link, "domains": list(self.domains),
            "judgements": list(self.judgements), "overall_rule": list(self.overall_rule),
            "companions": [{"name": n, "link": l, "why": w} for n, l, w in self.companions],
        }


ROB2 = Tool(
    "rob2", "RoB 2", "Cochrane risk of bias tool for randomised trials (version 2)",
    "randomised controlled trials", "https://www.riskofbias.info/welcome/rob-2-0-tool",
    ("Bias arising from the randomisation process",
     "Bias due to deviations from intended interventions",
     "Bias due to missing outcome data",
     "Bias in measurement of the outcome",
     "Bias in selection of the reported result"),
    ("Low risk", "Some concerns", "High risk"),
    ("If every domain is low risk, the study is low risk overall.",
     "If any domain is high risk, the study is high risk overall.",
     "Otherwise the study has some concerns overall."),
    (("RoB 2 Excel tool", "https://www.riskofbias.info/welcome/rob-2-0-tool/current-version-of-rob-2",
      "a free spreadsheet that works out each judgement from your answers"),
     ("robvis", "https://mcguinlu.shinyapps.io/robvis/",
      "a free website that turns your judgements into the traffic light figure journals expect")),
)
ROBINS_I = Tool(
    "robins_i", "ROBINS-I", "Risk Of Bias In Non-randomised Studies of Interventions",
    "non randomised studies of treatments (cohort, case control, before and after)",
    "https://www.riskofbias.info/welcome/robins-i-v2",
    ("Bias due to confounding", "Bias in classification of interventions",
     "Bias in selection of participants into the study",
     "Bias due to deviations from intended interventions", "Bias due to missing data",
     "Bias in measurement of outcomes", "Bias in selection of the reported result"),
    ("Low risk", "Moderate risk", "Serious risk", "Critical risk"),
    ("The overall judgement is the worst judgement given to any domain.",
     "If several domains are serious, consider rating the study critical overall."),
    (("robvis", "https://mcguinlu.shinyapps.io/robvis/",
      "a free website that turns your judgements into a traffic light figure"),),
)
QUADAS2 = Tool(
    "quadas2", "QUADAS-2", "Quality Assessment of Diagnostic Accuracy Studies 2",
    "studies of how accurate a test is", "https://www.bristol.ac.uk/population-health-sciences/projects/quadas/quadas-2/",
    ("Patient selection", "Index test", "Reference standard", "Flow and timing"),
    ("Low risk", "Unclear risk", "High risk"),
    ("If every domain is low risk, the study is low risk overall.",
     "If any domain is high risk, the study is high risk overall.",
     "Otherwise the overall risk is unclear."),
)
PROBAST = Tool(
    "probast", "PROBAST", "Prediction model Risk Of Bias ASsessment Tool",
    "studies that build, test or update a prediction model", "https://www.probast.org/",
    ("Participants", "Predictors", "Outcome", "Analysis"),
    ("Low risk", "Unclear risk", "High risk"),
    ("If every domain is low risk, the study is low risk overall.",
     "If any domain is high risk, the study is high risk overall.",
     "Otherwise the overall risk is unclear."),
    (("CHARMS checklist", "https://doi.org/10.1371/journal.pmed.1001744",
      "tells you exactly which details to extract from each prediction model study"),),
)
QUIPS = Tool(
    "quips", "QUIPS", "Quality In Prognosis Studies tool",
    "studies of a single prognostic factor", "https://methods.cochrane.org/prognosis/tools",
    ("Study participation", "Study attrition", "Prognostic factor measurement",
     "Outcome measurement", "Study confounding", "Statistical analysis and reporting"),
    ("Low risk", "Moderate risk", "High risk"),
    ("If every domain is low risk, or one is moderate, the study is low risk overall.",
     "If any domain is high risk, the study is high risk overall.",
     "Otherwise the study is moderate risk overall."),
)
NOS = Tool(
    "nos", "Newcastle-Ottawa Scale", "Newcastle-Ottawa Scale for cohort and case control studies",
    "cohort and case control studies", "https://www.ohri.ca/programs/clinical_epidemiology/oxford.asp",
    ("Selection (up to 4 stars)", "Comparability (up to 2 stars)",
     "Outcome or exposure (up to 3 stars)"),
    ("Good", "Fair", "Poor"),
    ("Add up the stars for each domain.",
     "Good: 3 or 4 selection stars, 1 or 2 comparability stars and 2 or 3 outcome stars.",
     "Poor: 0 or 1 selection stars, or 0 comparability stars, or 0 or 1 outcome stars.",
     "Anything in between is fair."),
)
ROBIS = Tool(
    "robis", "ROBIS", "Risk Of Bias In Systematic reviews",
    "systematic reviews (when the papers you review are themselves reviews)",
    "https://www.bristol.ac.uk/population-health-sciences/projects/robis/",
    ("Study eligibility criteria", "Identification and selection of studies",
     "Data collection and study appraisal", "Synthesis and findings"),
    ("Low risk", "Unclear risk", "High risk"),
    ("Judge each domain, then make an overall judgement in phase 3 of the tool.",
     "If any domain is high risk, the review is usually high risk overall.",
     "If every domain is low risk, the review is low risk overall."),
    (("AMSTAR 2", "https://amstar.ca/Amstar-2.php",
      "a 16 item checklist that rates overall confidence in a review as high, moderate, low "
      "or critically low"),),
)
CASP = Tool(
    "casp", "CASP checklists", "Critical Appraisal Skills Programme checklists",
    "appraising key studies in a literature or narrative review",
    "https://casp-uk.net/casp-tools-checklists/",
    ("Are the results valid?", "What are the results?", "Will the results help locally?"),
    ("Yes", "Can't tell", "No"),
    ("CASP checklists do not give a score. Use your answers to describe the strengths and "
     "weaknesses of each key study in your review.",),
    (("JBI critical appraisal tools", "https://jbi.global/critical-appraisal-tools",
      "free checklists for almost every study design"),),
)

TOOLS = {t.key: t for t in (ROB2, ROBINS_I, QUADAS2, PROBAST, QUIPS, NOS, ROBIS, CASP)}


def choose_tools(designs: str, axis: str = "", *, systematic: bool = True) -> list[Tool]:
    """The tool(s) for the designs a review includes, most important first."""
    d = f"{designs} {axis}".lower()
    if any(w in d for w in ("systematic review", "reviews of", "review of reviews",
                            "umbrella", "meta-review", "overview of reviews", "discordance")):
        return [ROBIS]
    if "diagnostic" in d or "accuracy" in d:
        return [QUADAS2]
    if "prediction model" in d or "prognostic model" in d:
        return [PROBAST]
    if "prognostic factor" in d:
        return [QUIPS]
    randomised = "random" in d or re.search(r"\brcts?\b", d) is not None
    non_randomised = any(w in d for w in ("cohort", "case-control", "case control",
                                          "observational", "non-randomised",
                                          "non-randomized", "quasi", "before and after"))
    out: list[Tool] = []
    if randomised:
        out.append(ROB2)
    if non_randomised:
        out.append(NOS if not randomised and "intervention" not in d else ROBINS_I)
    if not out:
        out = [ROBINS_I]
    if not systematic:
        out = [CASP, *out]
    return out
