from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from guide_pipeline.osf import (
    ApiSource,
    OsfError,
    OsfMirror,
    OsfRecord,
    delta_refresh,
    full_harvest,
    keep,
    parse_registration,
)
from guide_pipeline.prospero import StaleMirrorError


def reg(rid, title, *, desc="", schema="OSF Preregistration", created="2026-03-04T10:00:00",
        modified=None, subjects=(), withdrawn=False):
    return {"id": rid, "type": "registrations", "attributes": {
        "title": title, "description": desc, "registration_supplement": schema,
        "date_registered": created, "date_created": created,
        "date_modified": modified or created,
        "subjects": [[{"id": "x", "text": s} for s in subjects]] if subjects else [],
        "tags": [], "withdrawn": withdrawn}}


SR = "Generalized Systematic Review Registration"


# -- the filter ---------------------------------------------------------------
def test_filter_keeps_health_evidence_synthesis_only():
    sr_template = parse_registration(reg("a", "Exercise and cardiac function in adults on dialysis",
                                         schema=SR, subjects=["Medicine and Health Sciences"]))
    keyword = parse_registration(reg("b", "Task sharing for schizophrenia: a systematic review"))
    no_subject_health_words = parse_registration(
        reg("c", "Birth plan use: a scoping review", desc="Pregnant women in hospital care."))
    not_health = parse_registration(reg("d", "AI in HR decisions: a systematic review",
                                        schema=SR, subjects=["Social and Behavioral Sciences"]))
    not_review = parse_registration(reg("e", "Theta tACS and memory in patients: an RCT",
                                        subjects=["Medicine and Health Sciences"]))
    assert [keep(r) for r in (sr_template, keyword, no_subject_health_words, not_health,
                              not_review)] == [True, True, True, False, False]


def test_parse_registration_flattens_subjects_and_dates():
    r = parse_registration(reg("zrws4", "<b>Title</b>", subjects=["Medicine and Health Sciences",
                                                                 "Nursing"],
                               created="2026-10-24T18:21:56.027350"))
    assert r.title == "Title"
    assert r.subjects == ("Medicine and Health Sciences", "Nursing")
    assert r.date_registered == date(2026, 10, 24)
    assert r.link == "https://osf.io/zrws4/"


# -- the API adapter ----------------------------------------------------------
class FakeOsf:
    """Pages a fixed list of registrations by date_created or date_modified."""

    def __init__(self, items, page_size=2):
        self.items, self.page_size, self.requests = items, page_size, 0
        self.fail_next = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.fail_next:
            self.fail_next -= 1
            return httpx.Response(503)
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        field = next(k.split("[")[1].rstrip("]") for k in q if k.endswith("[gte]"))
        lo, hi = q[f"filter[{field}][gte]"], q[f"filter[{field}][lt]"]
        hits = [i for i in self.items if lo <= i["attributes"][field][:10] < hi]
        size = min(int(q["page[size]"]), self.page_size)
        page = int(q.get("page", 1))
        chunk = hits[(page - 1) * size: page * size]
        nxt = None
        if page * size < len(hits):
            nxt = str(request.url.copy_merge_params({"page": str(page + 1)}))
        return httpx.Response(200, json={"data": chunk,
                                         "links": {"next": nxt, "meta": {"total": len(hits)}}})


def source(fake):
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return ApiSource(client=client, min_interval=0, sleep=lambda s: None, backoff_base=0)


def test_api_source_pages_through_a_window():
    items = [reg(f"r{i}", f"Review {i}", created=f"2026-03-0{i}T00:00:00") for i in range(1, 6)]
    src = source(FakeOsf(items))
    assert src.count_window(date(2026, 3, 1), date(2026, 4, 1)) == 5
    got = src.fetch_window(date(2026, 3, 1), date(2026, 4, 1))
    assert [r.id for r in got] == ["r1", "r2", "r3", "r4", "r5"]


def test_api_source_retries_server_errors():
    fake = FakeOsf([reg("r1", "Review")])
    fake.fail_next = 2
    assert source(fake).count_window(date(2026, 3, 1), date(2026, 4, 1)) == 1


def test_api_source_raises_on_client_error():
    def handler(request):
        return httpx.Response(400, json={"errors": [{"detail": "bad filter"}]})
    src = ApiSource(client=httpx.Client(transport=httpx.MockTransport(handler)),
                    min_interval=0, sleep=lambda s: None)
    with pytest.raises(OsfError):
        src.count_window(date(2026, 3, 1), date(2026, 4, 1))


def test_api_source_sends_token_when_set():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [], "links": {"meta": {"total": 0}}})
    src = ApiSource(client=httpx.Client(transport=httpx.MockTransport(handler)), token="t0k",
                    min_interval=0, sleep=lambda s: None)
    src.count_window(date(2026, 3, 1), date(2026, 4, 1))
    assert seen["auth"] == "Bearer t0k"


# -- harvest and delta pull ---------------------------------------------------
HEALTH = ["Medicine and Health Sciences"]


def test_full_harvest_keeps_filtered_records_and_logs_coverage(tmp_path):
    items = [
        reg("a", "Statins and falls: a systematic review", subjects=HEALTH,
            created="2026-01-15T00:00:00"),
        reg("b", "Memory and theta: an experiment", subjects=HEALTH, created="2026-02-02T00:00:00"),
        reg("c", "Exercise in dialysis", schema=SR, subjects=HEALTH, created="2026-03-20T00:00:00"),
    ]
    mirror = OsfMirror(tmp_path / "osf.sqlite")
    summary = full_harvest(source(FakeOsf(items)), mirror, start=date(2026, 1, 1),
                           end=date(2026, 3, 31))
    assert (summary.seen, summary.kept, summary.added) == (3, 2, 2)
    assert mirror.record_count() == 2 and not mirror.has("b")
    assert mirror.coverage().covered_to == date(2026, 3, 31)


def test_delta_refresh_adds_new_and_marks_withdrawn(tmp_path):
    first = [reg("a", "Statins and falls: a systematic review", subjects=HEALTH,
                 created="2026-01-15T00:00:00")]
    mirror = OsfMirror(tmp_path / "osf.sqlite")
    full_harvest(source(FakeOsf(first)), mirror, start=date(2026, 1, 1), end=date(2026, 1, 31))
    later = [
        reg("a", "Statins and falls: a systematic review", subjects=HEALTH,
            created="2026-01-15T00:00:00", modified="2026-02-03T00:00:00", withdrawn=True),
        reg("n", "Vitamin D in sepsis: a meta-analysis", subjects=HEALTH,
            created="2026-02-04T00:00:00"),
    ]
    summary = delta_refresh(source(FakeOsf(later)), mirror, today=date(2026, 2, 5))
    assert (summary.added, summary.updated) == (1, 1)
    assert mirror.record_count() == 2
    assert mirror.record_count(include_withdrawn=False) == 1
    assert [m.id for m in mirror.search("statins falls")] == []  # withdrawn blocks nothing
    assert [m.id for m in mirror.search("vitamin d sepsis")] == ["n"]
    assert mirror.coverage().covered_to == date(2026, 2, 5)


def test_delta_refresh_needs_a_harvest_first(tmp_path):
    with pytest.raises(OsfError):
        delta_refresh(source(FakeOsf([])), OsfMirror(tmp_path / "osf.sqlite"))


def test_harvest_splits_a_crowded_window(tmp_path, monkeypatch):
    from guide_pipeline.osf import service

    monkeypatch.setattr(service, "WINDOW_MAX", 2)
    items = [reg(f"r{i}", f"Sepsis review {i}: a systematic review", subjects=HEALTH,
                 created=f"2026-01-{i:02d}T00:00:00") for i in range(1, 8)]
    mirror = OsfMirror(tmp_path / "osf.sqlite")
    summary = full_harvest(source(FakeOsf(items)), mirror, start=date(2026, 1, 1),
                           end=date(2026, 1, 31))
    assert summary.added == 7 and summary.windows > 1


# -- staleness guard and search ---------------------------------------------
def test_staleness_guard(tmp_path):
    mirror = OsfMirror(tmp_path / "osf.sqlite")
    with pytest.raises(StaleMirrorError):
        mirror.ensure_fresh(max_age_days=10, today=date(2026, 10, 24))
    mirror.log_refresh("automated", covered_to=date(2026, 10, 10), seen=0, added=0, updated=0)
    with pytest.raises(StaleMirrorError):
        mirror.ensure_fresh(max_age_days=10, today=date(2026, 10, 24))
    assert mirror.ensure_fresh(max_age_days=14, today=date(2026, 10, 24)).covered_to == date(
        2026, 10, 10)


def test_search_respects_a_registration_cutoff(tmp_path):
    mirror = OsfMirror(tmp_path / "osf.sqlite")
    mirror.merge([
        OsfRecord("old", "Vitamin D in sepsis: a systematic review",
                  date_registered=date(2025, 5, 1),
                  date_modified=datetime(2025, 5, 1, tzinfo=timezone.utc)),
        OsfRecord("new", "Vitamin D and sepsis mortality: a meta-analysis",
                  date_registered=date(2026, 5, 1)),
    ])
    assert {m.id for m in mirror.search("vitamin d sepsis")} == {"old", "new"}
    assert [m.id for m in mirror.search("vitamin d sepsis",
                                        registered_before=date(2026, 1, 1))] == ["old"]
    assert set(mirror.texts()) == {"old", "new"}
