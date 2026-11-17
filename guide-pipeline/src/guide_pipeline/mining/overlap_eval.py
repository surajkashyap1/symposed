"""Evaluate the overlap judge on labelled pairs (spec, Backtesting protocol).

Each pair is a candidate question and one record, labelled by a person as
"duplicate" (the record already answers or registers the question) or
"different". The record's title and text are fetched from PubMed, or from a
mirror, never typed into the file (rule 1). The judge sees each pair alone.

The decision that matters is "duplicate with high or medium confidence",
because it rejects a candidate outright. Precision: of the pairs it rejects, how many are
true duplicates (a false rejection throws away a good question). Recall: of
the true duplicates, how many it rejects (a miss lets a duplicate through to
screening, where the person still sees the flagged overlap). Both are reported,
with the full table of levels for each label, and appended to a history file.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..llm import LLMClient, LLMError
from .models import Pico, Question
from .overlap import Judgement, OverlapRecord, Retrieved, judge_many, rejects

LABELS = ("duplicate", "different")


@dataclass(frozen=True)
class Pair:
    id: str
    label: str
    question: Question
    record_ref: dict
    note: str = ""


@dataclass(frozen=True)
class PairSet:
    name: str
    pairs: tuple[Pair, ...]
    status: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "PairSet":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        pairs = []
        for p in d["pairs"]:
            if p["label"] not in LABELS:
                raise ValueError(f"pair {p['id']}: label must be one of {LABELS}")
            # "proposed_question" / "published_review" (older files: candidate / record)
            c = p.get("proposed_question") or p["candidate"]
            ref = p.get("published_review") or p.get("record") or {}
            ref = {k: v for k, v in ref.items() if k in ("pmid", "prospero", "osf")}
            pairs.append(Pair(str(p["id"]), p["label"],
                              Question(f"pair-{p['id']}", c["title"], Pico.from_dict(c)),
                              ref, p.get("note", "")))
        return cls(d.get("name", Path(path).stem), tuple(pairs), d.get("status", ""))


def resolve_records(pairs: tuple[Pair, ...], *, pubmed: Any, prospero: Any = None,
                    osf: Any = None) -> dict[str, Optional[OverlapRecord]]:
    """{pair id: record}, None where the record could not be found."""
    from .overlap import OsfRegistry, ProsperoRegistry

    pmids = [str(p.record_ref["pmid"]) for p in pairs if "pmid" in p.record_ref]
    papers = {x.pmid: x for x in pubmed.fetch_details(pmids)} if pmids else {}
    out: dict[str, Optional[OverlapRecord]] = {}
    for p in pairs:
        ref = p.record_ref
        rec: Optional[OverlapRecord] = None
        if "pmid" in ref and str(ref["pmid"]) in papers:
            rec = OverlapRecord.from_paper(papers[str(ref["pmid"])])
        elif "prospero" in ref and prospero is not None:
            rec = next(iter(ProsperoRegistry(prospero).get([ref["prospero"]])), None)
        elif "osf" in ref and osf is not None:
            rec = next(iter(OsfRegistry(osf).get([ref["osf"]])), None)
        out[p.id] = rec
    return out


@dataclass
class PairResult:
    pair: Pair
    record: Optional[OverlapRecord]
    judgement: Optional[Judgement]
    error: str = ""

    @property
    def rejects(self) -> bool:
        j = self.judgement
        return bool(j and j.judged and rejects(j))

    def as_dict(self) -> dict:
        j = self.judgement
        return {"id": self.pair.id, "label": self.pair.label, "note": self.pair.note,
                "candidate": self.pair.question.title,
                "record": self.record.as_dict() if self.record else self.pair.record_ref,
                "overlap": j.level if j else None, "confidence": j.confidence if j else None,
                "reasoning": j.reasoning if j else {}, "rejects": self.rejects,
                "error": self.error}


@dataclass
class EvalResult:
    name: str
    results: list[PairResult] = field(default_factory=list)

    @property
    def judged(self) -> list[PairResult]:
        return [r for r in self.results if r.judgement and r.judgement.judged]

    def _count(self, label: str, rejects: bool) -> int:
        return sum(1 for r in self.judged if r.pair.label == label and r.rejects == rejects)

    @property
    def precision(self) -> Optional[float]:
        tp, fp = self._count("duplicate", True), self._count("different", True)
        return tp / (tp + fp) if tp + fp else None

    @property
    def recall(self) -> Optional[float]:
        tp, fn = self._count("duplicate", True), self._count("duplicate", False)
        return tp / (tp + fn) if tp + fn else None

    def table(self) -> dict[str, dict[str, int]]:
        """{label: {"level, confidence": n}} over judged pairs."""
        out: dict[str, Counter] = {lbl: Counter() for lbl in LABELS}
        for r in self.judged:
            out[r.pair.label][f"{r.judgement.level}, {r.judgement.confidence}"] += 1
        return {k: dict(v) for k, v in out.items()}

    def summary(self) -> dict:
        return {
            "name": self.name, "pairs": len(self.results), "judged": len(self.judged),
            "true_duplicates_rejected": self._count("duplicate", True),
            "true_duplicates_missed": self._count("duplicate", False),
            "false_rejections": self._count("different", True),
            "different_kept": self._count("different", False),
            "precision": self.precision, "recall": self.recall, "table": self.table(),
        }


def run_eval(llm: LLMClient, pair_set: PairSet, records: dict[str, Optional[OverlapRecord]]
             ) -> EvalResult:
    result = EvalResult(pair_set.name)
    ready = [p for p in pair_set.pairs if records.get(p.id)]
    judged = judge_many(llm, [(p.question, [Retrieved(records[p.id], 0.0)]) for p in ready])
    by_id = dict(zip((p.id for p in ready), judged))
    for p in pair_set.pairs:
        rec = records.get(p.id)
        if rec is None:
            result.results.append(PairResult(p, None, None, "record not found"))
            continue
        out = by_id[p.id]
        if isinstance(out, LLMError):
            result.results.append(PairResult(p, rec, None, str(out)))
        else:
            result.results.append(PairResult(p, rec, out[0] if out else None))
    return result


def append_history(path: str | Path, result: EvalResult, *, model: str) -> None:
    entry = {"at": datetime.now(timezone.utc).isoformat(), "model": model, **result.summary()}
    path = Path(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
