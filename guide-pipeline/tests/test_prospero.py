import json
from datetime import date

import httpx
import pytest

from guide_pipeline.prospero import (
    EndpointSource,
    ProsperoError,
    ProsperoMirror,
    ProsperoRecord,
    StaleMirrorError,
    check_title,
    delta_refresh,
    full_harvest,
    import_export_file,
    match_key,
    parse_export,
    similarity,
)


def ris(rid, title, dp="23/09/2026"):
    return (
        f"TY  - JOUR\nID  - {rid}\nAU  - A Author; B Author\nTI  - {title}\n"
        f"DP  - {dp}\nYR  - {dp[-4:]}\nDB  - PROSPERO\n"
        f"SO  - https://www.crd.york.ac.uk/PROSPERO/view/{rid}\nER  -\n"
    )


def rec(rid, title, d=date(2026, 9, 23)):
    return ProsperoRecord(registration_id=rid, title=title, registration_date=d)


# -- parsing (the manual-upload route) ---------------------------------------
def test_parse_ris_export():
    text = ris("CRD1", "Vitamin D in sepsis") + ris("CRD2", "Delirium <i>after</i> surgery", "01/02/2025")
    out = parse_export(text)
    assert [r.registration_id for r in out] == ["CRD1", "CRD2"]
    assert out[0].registration_date == date(2026, 9, 23)
    assert out[1].title == "Delirium after surgery"  # markup stripped
    assert out[1].registration_date == date(2025, 2, 1)


def test_parse_csv_export():
    text = "Registration ID,Title,Date of registration,Review status\nCRD9,\"Statins, and falls\",2024-05-06,Ongoing\n"
    (r,) = parse_export(text)
    assert r.registration_id == "CRD9" and r.title == "Statins, and falls"
    assert r.registration_date == date(2024, 5, 6) and r.status == "Ongoing"


def test_parse_export_rejects_unknown_format():
    with pytest.raises(ProsperoError):
        parse_export("just,some\nrandom,csv\n")


# -- matching -----------------------------------------------------------------
def test_match_key_drops_stop_and_boilerplate_words():
    key = match_key("A Systematic Review and Meta-Analysis of Vitamin D in the Critically Ill")
    assert key == "vitamin d critically ill"


def test_similarity_ranks_paraphrase_above_unrelated():
    a = match_key("High-dose vitamin D supplementation and mortality in critically ill adults")
    para = match_key("Mortality with high dose vitamin D in critically ill adult patients: a systematic review")
    other = match_key("Melatonin for delirium prevention in older surgical patients")
    assert similarity(a, a) == pytest.approx(1.0)
    assert similarity(a, para) > 0.6
    assert similarity(a, other) < 0.2


# -- mirror -------------------------------------------------------------------
def test_mirror_merge_is_an_upsert(tmp_path):
    m = ProsperoMirror(tmp_path / "p.sqlite")
    first = m.merge([rec("CRD1", "Old title"), rec("CRD2", "Other")])
    assert (first.added, first.updated) == (2, 0)
    second = m.merge([rec("CRD1", "New title"), rec("CRD3", "Third")])
    assert (second.added, second.updated) == (1, 1)
    assert m.record_count() == 3
    assert m.search("New title", limit=1)[0].registration_id == "CRD1"
    assert not m.search("Old title", review_threshold=0.9)  # index updated too


def test_mirror_search_returns_near_matches_scored(tmp_path):
    m = ProsperoMirror(tmp_path / "p.sqlite")
    m.merge(
        [
            rec("CRD1", "Vitamin D supplementation and mortality in critically ill adults"),
            rec("CRD2", "Vitamin D and bone density in postmenopausal women"),
            rec("CRD3", "Melatonin for postoperative delirium"),
        ]
    )
    hits = m.search("Effect of vitamin D supplementation on mortality in critically ill adults")
    assert hits[0].registration_id == "CRD1" and hits[0].score > 0.6
    assert "CRD3" not in [h.registration_id for h in hits]
    assert hits[0].url.endswith("/view/CRD1")


def test_staleness_guard(tmp_path):
    m = ProsperoMirror(tmp_path / "p.sqlite")
    with pytest.raises(StaleMirrorError, match="never been refreshed"):
        m.ensure_fresh(max_age_days=10, today=date(2026, 9, 25))
    m.log_refresh("automated", covered_to=date(2026, 9, 10), added=5, updated=0)
    with pytest.raises(StaleMirrorError, match="15 days old"):
        m.ensure_fresh(max_age_days=10, today=date(2026, 9, 25))
    m.log_refresh("automated", covered_to=date(2026, 9, 20), added=1, updated=0)
    assert m.ensure_fresh(max_age_days=10, today=date(2026, 9, 25)).covered_to == date(2026, 9, 20)


# -- endpoint adapter (mocked) ------------------------------------------------
class FakeProspero:
    """Mimics the search endpoint: records keyed by registration date."""

    def __init__(self, records):
        self.records = records  # list of (rid, title, date)
        self.requests = []

    def _in(self, flt):
        if not flt:
            return self.records
        lo, hi = flt[0]["value"][0].split(" to ")
        parse = lambda s: date(int(s[6:]), int(s[3:5]), int(s[:2]))  # noqa: E731
        return [r for r in self.records if parse(lo) <= r[2] <= parse(hi)]

    def __call__(self, request):
        assert request.headers["prospero-auth-token"]  # the site's timestamp header
        body = json.loads(request.content)
        self.requests.append(body)
        hits = self._in(body["filters"])
        if body["term"] != "*":  # accession prefix, e.g. "(CRD42020*):AN"
            prefix = body["term"][1:].split("*")[0]
            hits = [h for h in hits if h[0].startswith(prefix)]
        docs = []
        if body["download"]:
            docs = [
                {"_source": {"ris": ris(rid, t, d.strftime("%d/%m/%Y"))}}
                for rid, t, d in hits[:10000]
            ]
        return httpx.Response(
            200,
            json=[{"hits": len(hits), "retvals": {"hits": {"hits": docs}}}],
        )


def source_for(fake, cap=10000):
    return EndpointSource(
        client=httpx.Client(transport=httpx.MockTransport(fake)),
        min_interval=0,
        sleep=lambda _s: None,
        export_cap=cap,
    )


def test_endpoint_count_and_fetch():
    fake = FakeProspero([("CRD1", "A", date(2026, 9, 1)), ("CRD2", "B", date(2026, 9, 20))])
    src = source_for(fake)
    assert src.count_range(date(2026, 9, 10), date(2026, 9, 30)) == 1
    (r,) = src.fetch_range(date(2026, 9, 10), date(2026, 9, 30))
    assert r.registration_id == "CRD2"
    assert fake.requests[-1]["filters"] == [
        {"name": "dateinprospero", "value": ["10/09/2026 to 30/09/2026"]}
    ]


def test_endpoint_error_payload_raises():
    def handler(request):
        return httpx.Response(200, json={"status": "error", "errormessage": "nope"})

    with pytest.raises(ProsperoError, match="nope"):
        source_for(handler).count_range(date(2026, 1, 1), date(2026, 1, 2))


def test_endpoint_truncated_export_raises():
    def handler(request):
        return httpx.Response(200, json=[{"hits": 5, "retvals": {"hits": {"hits": []}}}])

    with pytest.raises(ProsperoError, match="returned 0 of 5"):
        source_for(handler).fetch_range(date(2026, 1, 1), date(2026, 1, 2))


def test_endpoint_null_ris_rows_are_looked_up_by_id():
    def handler(request):
        body = json.loads(request.content)
        if not body["download"]:  # the per-ID lookup
            assert body["term"] == "(CRD7):AN"
            src = {"title": "<p>Looked up title</p>", "reviewstatus": "Ongoing"}
            return httpx.Response(
                200, json=[{"hits": 1, "retvals": {"hits": {"hits": [{"_source": src}]}}}]
            )
        docs = [
            {"_source": {"ris": ris("CRD1", "Fine")}, "sort": ["CRD1"]},
            {"_source": {"ris": None}, "sort": ["CRD7"]},
        ]
        return httpx.Response(200, json=[{"hits": 2, "retvals": {"hits": {"hits": docs}}}])

    src = source_for(handler)
    out = src.fetch_range(date(2015, 1, 1), date(2015, 12, 31))
    assert [(r.registration_id, r.title) for r in out] == [
        ("CRD1", "Fine"), ("CRD7", "Looked up title")
    ]
    assert out[1].status == "Ongoing" and src.unresolved == []


def test_endpoint_unresolvable_null_ris_is_reported_not_fatal():
    def handler(request):
        body = json.loads(request.content)
        if not body["download"]:
            return httpx.Response(200, json=[{"hits": 0, "retvals": {"hits": {"hits": []}}}])
        docs = [{"_source": {"ris": None}, "sort": ["CRD7"]}]
        return httpx.Response(200, json=[{"hits": 1, "retvals": {"hits": {"hits": docs}}}])

    src = source_for(handler)
    assert src.fetch_range(date(2015, 1, 1), date(2015, 1, 2)) == []
    assert src.unresolved == ["CRD7"]


def test_endpoint_withdrawn_rows_are_counted_separately():
    def handler(request):
        body = json.loads(request.content)
        if not body["download"]:
            src = {"title": None, "editingstatus": "withdrawn"}
            return httpx.Response(
                200, json=[{"hits": 1, "retvals": {"hits": {"hits": [{"_source": src}]}}}]
            )
        docs = [{"_source": {"ris": None}, "sort": ["CRD8"]}]
        return httpx.Response(200, json=[{"hits": 1, "retvals": {"hits": {"hits": docs}}}])

    src = source_for(handler)
    assert src.fetch_range(date(2016, 1, 1), date(2016, 1, 2)) == []
    assert src.withdrawn == ["CRD8"] and src.unresolved == []


def test_endpoint_retries_server_errors():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"hits": 0, "retvals": {"hits": {"hits": []}}}])

    assert source_for(handler).count_range(date(2026, 1, 1), date(2026, 1, 2)) == 0
    assert len(calls) == 3


# -- service: harvest, delta, manual import, check ----------------------------
def year_of_records():
    out = []
    d = date(2026, 1, 1)
    for i in range(40):
        out.append((f"CRD{i}", f"Title number {i}", date(2026, 1 + i % 9, 1 + i % 27)))
    return out + [("CRD99", "Early one", d)]


def test_full_harvest_splits_windows_over_the_cap(tmp_path):
    fake = FakeProspero(year_of_records())
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    summary = full_harvest(
        source_for(fake, cap=10), mirror, start=date(2026, 1, 1), end=date(2026, 9, 30)
    )
    assert mirror.record_count() == 41 and summary.added == 41
    downloads = [r for r in fake.requests if r["download"]]
    assert len(downloads) >= 5  # had to split: no single export over the cap
    last = mirror.last_refresh()
    assert last.mode == "automated" and last.covered_to == date(2026, 9, 30)


def test_harvest_splits_an_oversized_day_by_accession_prefix(tmp_path):
    day = date(2020, 4, 28)
    records = [(f"CRD420201{i:02d}", f"Bulk {i}", day) for i in range(25)]
    fake = FakeProspero(records)
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    summary = full_harvest(source_for(fake, cap=10), mirror, start=day, end=day)
    assert summary.added == 25 and mirror.record_count() == 25
    terms = {r["term"] for r in fake.requests if r["download"]}
    assert terms == {"(CRD4202010*):AN", "(CRD4202011*):AN", "(CRD4202012*):AN"}


def test_prefix_split_that_loses_records_raises(tmp_path):
    day = date(2020, 4, 28)
    # IDs outside the CRD scheme would be missed by the prefix partition.
    records = [(f"X{i}", "odd", day) for i in range(3)] + [
        (f"CRD9{i}", "t", day) for i in range(9)
    ]
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    with pytest.raises(ProsperoError, match="account for 9 of 12"):
        full_harvest(source_for(FakeProspero(records), cap=10), mirror, start=day, end=day)


def test_delta_refresh_pulls_since_last_refresh(tmp_path):
    fake = FakeProspero([("CRD1", "A", date(2026, 9, 1)), ("CRD2", "B", date(2026, 9, 24))])
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    with pytest.raises(ProsperoError, match="full harvest"):
        delta_refresh(source_for(fake), mirror, today=date(2026, 9, 25))
    mirror.log_refresh("automated", covered_to=date(2026, 9, 20), added=0, updated=0)
    summary = delta_refresh(source_for(fake), mirror, today=date(2026, 9, 25))
    assert summary.added == 1 and mirror.record_count() == 1  # only CRD2
    flt = fake.requests[-1]["filters"][0]["value"][0]
    assert flt == "19/09/2026 to 26/09/2026"  # 1-day overlap each side
    assert mirror.last_refresh().covered_to == date(2026, 9, 25)


def test_manual_import_merges_identically(tmp_path):
    path = tmp_path / "export.csv"  # the UI's "CSV" download is RIS text
    path.write_text(ris("CRD1", "Vitamin D in sepsis", "20/09/2026"))
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    summary = import_export_file(path, mirror)
    assert summary.added == 1
    last = mirror.last_refresh()
    assert last.mode == "manual" and last.covered_to == date(2026, 9, 20)


def test_check_title_records_dates_and_matches(tmp_path):
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    mirror.merge([rec("CRD1", "Vitamin D supplementation and mortality in critically ill adults")])
    mirror.log_refresh("automated", covered_to=date(2026, 9, 24), added=1, updated=0)
    result = check_title(
        mirror,
        "Vitamin D supplementation and mortality in critically ill adults: a systematic review",
        max_age_days=10,
        reject_threshold=0.6,
        review_threshold=0.35,
        today=date(2026, 9, 25),
    )
    assert result.verdict == "registered"
    assert result.checked_on == date(2026, 9, 25)
    assert result.mirror_covered_to == date(2026, 9, 24)
    assert result.search_terms == "vitamin d supplementation mortality critically ill adults"
    d = result.as_dict()
    assert d["checked_on"] == "2026-09-25" and d["matches"][0]["registration_id"] == "CRD1"


def test_check_title_verdicts_and_staleness(tmp_path):
    mirror = ProsperoMirror(tmp_path / "p.sqlite")
    mirror.merge([rec("CRD1", "Vitamin D and bone density in postmenopausal women")])
    mirror.log_refresh("automated", covered_to=date(2026, 9, 24), added=1, updated=0)
    kw = dict(max_age_days=10, reject_threshold=0.6, review_threshold=0.2)
    clear = check_title(mirror, "Melatonin for delirium", today=date(2026, 9, 25), **kw)
    assert clear.verdict == "clear" and not clear.matches
    near = check_title(mirror, "Vitamin D and falls in older women", today=date(2026, 9, 25), **kw)
    assert near.verdict == "review"
    with pytest.raises(StaleMirrorError):
        check_title(mirror, "anything", today=date(2026, 10, 30), **kw)
