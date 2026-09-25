from datetime import date

from guide_pipeline.gates import (
    DOWNGRADE,
    FLAG,
    PASS,
    REJECT,
    TriageCounts,
    apply_gates,
    records_cap,
)
from guide_pipeline.prospero import ProsperoCheck, ProsperoMatch
from guide_pipeline.settings import Thresholds

TH = Thresholds(
    min_eligible_studies=8,
    scoping_min_studies=5,
    max_records_to_screen=400,
    prospero_reject_similarity=0.75,
    prospero_review_similarity=0.45,
)


def counts(**kw):
    base = dict(
        records_to_screen=200,
        eligible_studies=30,
        recent_reviews=0,
        trials_reporting_soon=0,
        protocol_matches=[],
    )
    base.update(kw)
    return TriageCounts(**base)


def prospero(verdict="clear", score=None):
    matches = []
    if score is not None:
        matches = [ProsperoMatch("CRD1", "Registered", date(2025, 1, 1), score)]
    return ProsperoCheck(
        title="t",
        search_terms="t",
        checked_on=date(2026, 9, 25),
        mirror_covered_to=date(2026, 9, 25),
        mirror_refreshed_at=None,
        verdict=verdict,
        matches=matches,
    )


def gate(result, name):
    return next(g for g in result.gates if g.name == name)


def test_clean_candidate_passes_every_gate_with_numbers():
    r = apply_gates(counts(), prospero(), TH)
    assert r.outcome == PASS and r.passed
    assert {g.name for g in r.gates} == {
        "too_few_studies",
        "too_many_records",
        "already_reviewed",
        "registered_protocol",
        "trials_reporting_soon",
    }
    too_few = gate(r, "too_few_studies")
    assert (too_few.value, too_few.threshold) == (30, 8)


def test_too_few_downgrades_then_rejects():
    r = apply_gates(counts(eligible_studies=6), prospero(), TH)
    assert r.outcome == DOWNGRADE and not r.passed
    assert "scoping or narrative" in gate(r, "too_few_studies").detail
    assert apply_gates(counts(eligible_studies=2), prospero(), TH).outcome == REJECT


def test_scoping_request_only_needs_the_scoping_minimum():
    r = apply_gates(counts(eligible_studies=6), prospero(), TH, publication_type="scoping review")
    assert r.outcome == PASS


def test_too_many_records_scales_with_collaborators():
    assert records_cap(TH, collaborators=2) == 400
    assert records_cap(TH, collaborators=1) == 400  # dual screening minimum of two
    assert records_cap(TH, collaborators=4) == 800
    assert apply_gates(counts(records_to_screen=600), prospero(), TH).outcome == REJECT
    assert apply_gates(counts(records_to_screen=600), prospero(), TH, collaborators=4).passed


def test_recent_review_rejects():
    r = apply_gates(counts(recent_reviews=2), prospero(), TH)
    assert r.outcome == REJECT
    assert "2 systematic review" in gate(r, "already_reviewed").detail


def test_registered_protocol_uses_prospero_and_pubmed_protocols():
    assert apply_gates(counts(), prospero("registered", 0.8), TH).outcome == REJECT
    assert apply_gates(counts(), prospero("review", 0.5), TH).outcome == FLAG
    published = [("123", "A published protocol", 0.8)]
    r = apply_gates(counts(protocol_matches=published), prospero(), TH)
    assert r.outcome == REJECT
    g = gate(r, "registered_protocol")
    assert g.value == 0.8 and "PMID 123" in g.detail
    # a distant match is not named in the reason
    r = apply_gates(counts(protocol_matches=[("7", "far", 0.1)]), prospero("review", 0.5), TH)
    assert "PMID 7" not in gate(r, "registered_protocol").detail


def test_trials_reporting_soon_flags_not_rejects():
    r = apply_gates(counts(trials_reporting_soon=2), prospero(), TH)
    assert r.outcome == FLAG and r.passed
    unknown = apply_gates(counts(trials_reporting_soon=None), prospero(), TH)
    assert unknown.outcome == FLAG and "could not be checked" in gate(
        unknown, "trials_reporting_soon"
    ).detail


def test_reject_outranks_downgrade_and_flag():
    r = apply_gates(
        counts(eligible_studies=6, trials_reporting_soon=1, recent_reviews=1), prospero(), TH
    )
    assert r.outcome == REJECT
    assert len(r.reasons) == 3  # every non-pass gate explains itself
