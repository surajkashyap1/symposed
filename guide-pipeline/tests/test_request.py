from guide_pipeline.candidates import RequestPreferences, generate_candidates
from guide_pipeline.request import from_proforma

SAMPLE = {
    "grade": "Foundation doctor",
    "specialties": ["Cardiology", "Respiratory medicine"],
    "topics": "Heart failure, inhaler technique",
    "publicationType": "Literature review",
    "hoursPerWeek": "Under 3",
    "timeline": "Within 3 months",
    "statsConfidence": "Basic",
    "databases": ["Unsure"],
    "collaborators": "2",
    "nonEnglish": "No",
    "anythingElse": None,
}


def test_old_proforma_defaults_to_strict_type_and_exact_topic():
    r = from_proforma(SAMPLE, order_id="o1")
    p = r.preferences
    assert (p.publication_type, p.type_flexible, p.topic_flexibility) == (
        "literature review", False, "exact"
    )
    assert p.collaborators == 3  # "2 other people" is a team of three
    assert r.generation_topic == "Heart failure, inhaler technique"
    assert "a Foundation doctor" in p.context and "Under 3 hours a week" in p.context
    assert "cannot read non-English papers" in p.context


def test_flexibility_answers_map_through():
    r = from_proforma({**SAMPLE, "publicationType": "Systematic review",
                       "typeFlexibility": "Flexible, another review type is fine",
                       "topicFlexibility": "Flexible within my specialty"})
    assert r.preferences.type_flexible and r.preferences.topic_flexibility == "specialty"
    not_sure = from_proforma({**SAMPLE, "publicationType": "Not sure, recommend one for me"})
    assert not_sure.preferences.publication_type == "systematic review"
    assert not_sure.preferences.type_flexible


def test_blank_topic_starts_from_the_specialties():
    r = from_proforma({**SAMPLE, "topics": "   "})
    assert r.blank_topic
    assert r.preferences.topic_flexibility == "specialty"  # blank topic widens scope
    assert "Cardiology or Respiratory medicine" in r.generation_topic
    assert r.search_topic == "Cardiology OR Respiratory medicine"


def test_blank_topic_and_no_specialty_is_fully_open():
    r = from_proforma({**SAMPLE, "topics": "", "specialties": ["Undecided"],
                       "specialtyUndecided": True})
    assert r.preferences.topic_flexibility == "any" and r.preferences.specialties == ()
    assert "any open clinical review question" in r.generation_topic
    assert r.search_topic == "clinical medicine"


def test_user_context_reaches_the_generation_prompt():
    class Capture:
        def __init__(self):
            self.user = ""

        def complete_json(self, system, user, schema=None, cache_system=False):
            self.user = user
            axes = ["Unexamined subgroup", "Unpooled outcome", "Superseded review",
                    "Indirect comparison", "Emerging technology", "Discordance"]
            return {"candidates": [{"title": f"T{i}", "axis": a, "pubmed_query": "q"}
                                   for i, a in enumerate(axes)]}

    llm = Capture()
    prefs = RequestPreferences(context="The user is a Foundation doctor; Under 3 hours a week.")
    generate_candidates(llm, "sedation", preferences=prefs)
    assert "The user is a Foundation doctor" in llm.user and "feasible for this user" in llm.user
