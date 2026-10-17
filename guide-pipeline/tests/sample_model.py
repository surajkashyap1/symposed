"""A made-up, realistic guide model for rendering tests and design review.

No customer data. PMIDs are fake (9-digit, starting 900).
"""

from guide_pipeline.guide_model import step_timeline, steps
from guide_pipeline.rob_tools import ROB2, ROBINS_I


def sample_model(systematic: bool = True) -> dict:
    papers = []
    types = [("Randomised controlled trial", "PubMed"), ("Cohort study of ICU adults", "our estimate"),
             ("Meta-analysis", "PubMed"), ("Observational study", "PubMed"),
             ("Not clear from the abstract", "our estimate")]
    for i in range(14):
        t, b = types[i % len(types)]
        papers.append({
            "n": i + 1, "pmid": f"9000000{i:02d}", "id_label": "PMID", "doi": f"10.9999/fake.{i}",
            "title": ["High dose vitamin D3 for critically ill adults with deficiency: a "
                      "multicentre randomised trial", "Vitamin D status and 90 day mortality in "
                      "intensive care", "Enteral cholecalciferol and length of stay after "
                      "major surgery requiring critical care"][i % 3],
            "year": 2024 - (i % 8), "first_published": 2024 - (i % 8),
            "journal": ["Critical Care Medicine", "Intensive Care Medicine",
                        "The New England Journal of Medicine"][i % 3],
            "first_author": ["Amrein K", "Ginde AA", "Smith JB", "Nair P"][i % 4],
            "authors": ["Amrein K", "Other A"], "abstract": "Background: made up abstract text. " * 6,
            "publication_type": t, "publication_type_basis": b,
            "sample_size": ["475 patients", "1,360 adults", "", "88"][i % 4],
            "population": "Critically ill adults", "url": f"https://pubmed.ncbi.nlm.nih.gov/9000000{i:02d}/",
            "full_text_open": i % 3 == 0,
        })
    tl, a = step_timeline(systematic=systematic, records=640, eligible=14, team=3,
                          hours_label="3 to 5")
    q = ('("Vitamin D"[Mesh] OR "vitamin D"[tiab] OR cholecalciferol[tiab] OR ergocalciferol[tiab]) '
         'AND ("Critical Illness"[Mesh] OR "critically ill"[tiab] OR "intensive care"[tiab] OR ICU[tiab]) '
         'AND (mortality[tiab] OR death[tiab] OR survival[tiab])')
    return {
        "version": 2, "title": "Does vitamin D supplementation reduce mortality in critically "
                               "ill adults with vitamin D deficiency?",
        "publication_type": "systematic review" if systematic else "literature review",
        "systematic": systematic, "generated_on": "2026-10-17", "search_date": "2026-10-17",
        "novelty_date": "17/10/2026", "prepared_for": "Alex",
        "profile": {"grade": "Foundation doctor", "hours": "3 to 5", "team": 3,
                    "databases": ["PubMed only", "Embase"], "stats": "Basic",
                    "timeline": "6 to 12 months", "specialties": ["Intensive care"]},
        "steps": steps(systematic),
        "pico": [["Population", "Adults (18 or over) treated in an intensive care unit with "
                                "low vitamin D levels"],
                 ["Intervention or exposure", "Vitamin D given by mouth, feeding tube or injection, any dose"],
                 ["Comparator", "Placebo or no vitamin D"],
                 ["Outcomes", "Death from any cause, length of stay, time on a ventilator"],
                 ["Study designs", "Randomised controlled trials"]],
        "rationale": "Low vitamin D is common in people treated in intensive care and is linked "
                     "with worse outcomes [1]. Trials of giving vitamin D have found mixed "
                     "results [2], and the largest recent trial was stopped early [3]. A new "
                     "review that brings these trials together would help doctors decide "
                     "whether to test and treat vitamin D in intensive care.",
        "references": ["Amrein K et al. (2014). Effect of high dose vitamin D3 on hospital length "
                       "of stay in critically ill patients. JAMA. PMID 900000001.",
                       "Ginde AA et al. (2019). Early high dose vitamin D3 for critically ill "
                       "adults. NEJM. PMID 900000002."],
        "similar": [{"title": "Vitamin D supplementation in critically ill adults: a meta-analysis "
                              "of randomised trials (2017)",
                     "url": "https://pubmed.ncbi.nlm.nih.gov/900000101/",
                     "difference": "That review searched up to 2016 and included patients with "
                                   "normal vitamin D levels. Yours focuses on deficiency and "
                                   "includes the large trials published since."},
                    {"title": "PROSPERO CRD42099000001: Vitamin D in sepsis",
                     "url": "https://www.crd.york.ac.uk/PROSPERO/view/CRD42099000001",
                     "difference": "Sepsis only. Your question covers all critically ill adults."}],
        "feasibility": {"eligible_triage": 31, "eligible_screened": 14, "records_to_screen": 640,
                        "recommended_team": 3},
        "searches": [
            {"number": 1, "name": "The search that found your suggested papers",
             "purpose": "This is the search we ran to find the papers listed in step 4.",
             "query": q + " AND randomized controlled trial[pt]", "count": 54,
             "recommended": False, "found_papers": True},
            {"number": 2, "name": "Sensitive", "purpose": "Finds as many relevant trials as "
             "possible, at the cost of more screening.", "query": q, "count": 640,
             "recommended": True, "found_papers": False},
            {"number": 3, "name": "Precise", "purpose": "A shorter search that finds the core "
             "trials quickly.", "query": q + " AND randomized[tiab]", "count": 121,
             "recommended": False, "found_papers": False}],
        "papers_search_number": 1, "recommended_search_number": 2,
        "recommendation_reason": "It finds every trial in our test set with a workable number of records.",
        "embase": "('vitamin d'/exp OR 'cholecalciferol'/exp) AND ('critical illness'/exp OR 'intensive care unit'/exp) AND ('mortality'/exp OR death:ti,ab)",
        "cochrane": '#1 MeSH descriptor: [Vitamin D] explode all trees\n#2 MeSH descriptor: [Critical Illness] explode all trees\n#3 #1 AND #2',
        "papers": papers,
        "own_access": [{"title": "Vitamin D in the ICU: a pilot trial", "doi": "10.9999/fake.x", "pmid": "900000099"}],
        "criteria": {"population": "Adults in intensive care with low vitamin D",
                     "intervention": "Vitamin D supplementation, any route or dose",
                     "comparator": "Placebo or usual care", "outcomes": "Death from any cause",
                     "designs": "Randomised controlled trials", "setting": "",
                     "other_inclusion": ["Published in English"],
                     "exclusion": ["Children under 18", "Conference abstracts with no full paper"]},
        "criteria_reasoning": [{"criterion": "Population", "reasoning": "Deficient patients are the group most likely to benefit."},
                               {"criterion": "Study designs", "reasoning": "Randomised trials give the fairest test of a treatment."}],
        "decision_tree": [
            {"question": "Is it a randomised controlled trial?", "no_label": "Wrong design: not randomised"},
            {"question": "Were the patients adults treated in intensive care?", "no_label": "Wrong population"},
            {"question": "Did one group receive vitamin D?", "no_label": "Wrong intervention"},
            {"question": "Was the other group given placebo or usual care?", "no_label": "Wrong comparator"},
            {"question": "Does it report deaths from any cause?", "no_label": "No mortality outcome"}],
        "exclusion_reasons": ["Wrong design: not randomised", "Wrong population", "Wrong intervention",
                              "Wrong comparator", "No mortality outcome", "Duplicate",
                              "Full text not available", "Other (write in notes)"],
        "prospero": ({"review_title": "Vitamin D and mortality in critically ill adults",
                      "review_question": "Does vitamin D reduce deaths?", "searches": "PubMed, Embase, CENTRAL",
                      "condition_or_domain": "Vitamin D deficiency in critical illness",
                      "population": "Adults in ICU", "intervention_exposure": "Vitamin D",
                      "comparator_control": "Placebo", "types_of_study": "RCTs",
                      "main_outcomes": "All cause mortality", "additional_outcomes": "Length of stay",
                      "data_extraction": "Two reviewers", "risk_of_bias_assessment": "RoB 2",
                      "strategy_for_synthesis": "Random effects meta-analysis",
                      "subgroup_analyses": "By dose"} if systematic else None),
        "rob_tools": [ROB2.as_dict()] if systematic else [ROBINS_I.as_dict()],
        "reporting": ["PRISMA 2020", "PRISMA-S for reporting the search", "SWiM if you synthesise without meta-analysis"],
        "aims": "To find out whether giving vitamin D to critically ill adults with low vitamin D reduces deaths.",
        "objectives": ["Combine the death rates from all eligible trials.", "Look at whether the dose matters.",
                       "Rate the certainty of the evidence with GRADE."],
        "analysis": "If at least three trials report deaths in a similar way, combine them in a random effects meta-analysis and show the results in a forest plot.",
        "skills": ["Basic use of RevMan or jamovi", "Reading a forest plot"],
        "extraction_fields": ["Study ID (first author, year)", "Country and setting", "Study design",
                              "Population and sample size", "Intervention or exposure", "Comparator",
                              "Outcomes and time points", "Results for each outcome",
                              "Funding and conflicts of interest"],
        "prisma": {"identified": 640, "preprints_identified": 3, "retrieved": 54, "duplicates_removed": 2,
                   "screened": 52, "excluded_estimate": 38, "full_text_to_assess": 14} if systematic else None,
        "structure": [["Introduction", ["Rationale", "Objectives (PICO)"]],
                      ["Methods", ["Protocol and registration", "Eligibility criteria", "Search"]],
                      ["Results", ["Study selection (PRISMA flow diagram)", "Study characteristics"]],
                      ["Discussion", ["Summary", "Limitations"]]],
        "timeline": tl, "timeline_assumptions": a,
        "journals": [["Critical Care Medicine", 5], ["Intensive Care Medicine", 4]],
        "search_appendix": [{"source": "PubMed", "query": q, "count": 640, "run_at": "2026-10-17T10:00:00"}],
        "warnings": [], "screenshots": {},
        "alternatives": [
            {"number": i, "title": t, "axis": "Gap in existing reviews",
             "rationale": "The closest reviews looked only at adults under 65, so this group is missing.",
             "why_novel": "On 17/10/2026 we found no recent systematic review in PubMed (last 10 years) and no close match on PROSPERO.",
             "eligible_estimate": e, "records_to_screen": r, "search_query": q, "search_count": r,
             "prospero_checked_on": "17/10/2026", "prospero_verdict": "clear", "trials_query": "vitamin d icu",
             "pico": [["Population", "Adults over 65 in intensive care"], ["Intervention or exposure", "Vitamin D"],
                      ["Comparator", "Placebo"], ["Outcomes", "Delirium"], ["Study designs", "Randomised trials"]]}
            for i, t, e, r in ((1, "Vitamin D and delirium in older adults in intensive care", 22, 180),
                               (2, "Vitamin D and ventilator-associated pneumonia in critically ill adults", 31, 260))],
        "glossary": [{"term": "PICO", "definition": "Population, Intervention, Comparator, Outcome."},
                     {"term": "Cholecalciferol", "definition": "The form of vitamin D made in the skin, also called vitamin D3."}],
    }
