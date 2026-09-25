import pytest

from guide_pipeline.__main__ import parse_candidate_args


def test_parse_candidate_args_reads_preferences():
    topic, prefs = parse_candidate_args(
        ["paediatric", "cardiology", "--type", "Narrative review", "--type-flexible",
         "--topic", "specialty", "--specialty", "Cardiology", "--collaborators", "3"]
    )
    assert topic == "paediatric cardiology"
    assert prefs.publication_type == "narrative review" and prefs.type_flexible
    assert prefs.topic_flexibility == "specialty" and prefs.specialties == ("Cardiology",)
    assert prefs.collaborators == 3


def test_parse_candidate_args_defaults_are_strict_systematic():
    topic, prefs = parse_candidate_args(["sepsis"])
    assert (topic, prefs.publication_type, prefs.type_flexible, prefs.topic_flexibility) == (
        "sepsis", "systematic review", False, "exact"
    )


def test_parse_candidate_args_rejects_unknown_values():
    with pytest.raises(ValueError):
        parse_candidate_args(["x", "--type", "case report"])
    with pytest.raises(ValueError):
        parse_candidate_args(["x", "--topic", "sort of"])
