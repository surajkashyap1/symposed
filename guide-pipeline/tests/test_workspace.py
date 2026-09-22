import json
from datetime import datetime, timezone

from guide_pipeline.workspace import Workspace, create_workspace, slugify


def test_slugify():
    assert slugify("Vitamin D & COVID-19 outcomes!") == "vitamin-d-covid-19-outcomes"
    assert slugify("") == "request"
    assert slugify("---") == "request"


def test_create_workspace_makes_dirs(tmp_path):
    ws = create_workspace(
        "Vitamin D in sepsis",
        base=tmp_path,
        now=datetime(2026, 9, 22, 8, 30, 0, tzinfo=timezone.utc),
    )
    assert ws.dir.exists()
    assert ws.cache_dir.is_dir()
    assert ws.dir.name == "20260922-083000_vitamin-d-in-sepsis"
    assert ws.results_path == ws.dir / "results.json"
    assert ws.guide_path == ws.dir / "guide.docx"


def test_create_workspace_with_explicit_request_id(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="order-42")
    assert ws.dir.name == "order-42"


def test_write_results_roundtrip(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r1")
    path = ws.write_results({"count": 123, "topic": "café"})
    assert path == ws.results_path
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == {"count": 123, "topic": "café"}


def test_workspace_is_reusable_for_same_name(tmp_path):
    a = create_workspace(base=tmp_path, request_id="same")
    b = create_workspace(base=tmp_path, request_id="same")
    assert a.dir == b.dir
    assert isinstance(a, Workspace)
