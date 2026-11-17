"""The two agentic filters of the update pipeline (Samarth, 2026-10-27).

Step 3b (triage) runs after step 3 and before full texts are asked for: the
decision model reads the candidate reviews, searches for itself and shortlists
five options, each a direct update or a reworked angle. Only those five need
full texts. Step 5b (appraisal) runs once the full texts are in and step 5 has
counted the direct updates: it reads the full texts, searches again and selects
the one option the guide is written for.

Each stage's prompt is a markdown file in AGENT_PROMPTS_DIR, read fresh every
time the stage runs, so it can be edited without touching code. Everything after
"=== PROMPT START ===" becomes the system prompt, its {{placeholders}} filled
here. The notes above that line are for people and never sent.

Tools: pubmed_search, pubmed_fetch, registry_search and db_lookup run here,
web_search and web_fetch on Anthropic's servers. PROSPERO and OSF are reached
only through the local mirrors (registry_search): the web tools are barred from
both sites, as the pipeline never queries either registry title by title. Rule 1 holds by checking: every PubMed count
and PMID the model reports is compared with what the tools returned, and
anything not found there is marked unverified. A finished stage is saved
(stage1.json, stage2.json) and reused on the next run: delete the file to run
the stage again.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from ..llm import CALL_RETRIES, RETRY_WAIT_SECONDS, UsageMeter, task_config, transport_errors
from ..sources.pubmed import Paper
from .reviews import citation

STAGE1_PROMPT = "stage1_triage_prompt.md"
STAGE2_PROMPT = "stage2_fulltext_appraisal_prompt.md"
STAGE1_JSON, STAGE2_JSON = "stage1.json", "stage2.json"
MARKER = "=== PROMPT START ==="
CONTEXT_BETA = "context-management-2025-06-27"
FALLBACK_DEFAULT_BETA = "server-side-fallback-2026-07-01"  # fallbacks: "default"
FALLBACK_LIST_BETA = "server-side-fallback-2026-06-01"     # fallbacks: [{"model": ...}]
# Old tool results are cleared rarely and in large batches. The defaults (from
# 100k tokens, keep 3, clear every turn) left the agent only its last 3 results
# and rewrote the prompt cache each turn: $7.76 of Step 3b's $10.39 on req02.
CONTEXT_EDIT = {"type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 400_000},
                "keep": {"type": "tool_uses", "value": 30},
                "clear_at_least": {"type": "input_tokens", "value": 150_000}}
MAX_OUTPUT_TOKENS = 64000
WEB_SEARCH_USD = 0.01        # $10 per 1,000 searches, on top of tokens
MAX_PMIDS_RETURNED = 200     # pubmed_search lists at most this many PMIDs
MAX_FETCH = 50               # pubmed_fetch reads at most this many records per call
ABSTRACT_CHARS = 3000        # pubmed_fetch shortens longer abstracts, and says so
BUDGET_TEXT = ("The tool budget for this stage is used up. Do not call any more tools. "
               "Write your summary and the <final_output> JSON now from what you have, and "
               "say in assumptions which checks you could not finish.")
REGISTRY_LIMIT = 15          # registry_search returns at most this many per registry
# The registries are read from their local mirrors only (CLAUDE.md), never live.
REGISTRY_DOMAINS = ["crd.york.ac.uk", "osf.io"]
NOT_CHECKED = ("The PROSPERO and OSF copies are not in use in this testing run "
               "(SKIP_REGISTRY_MIRRORS=true): the registries cannot be checked. Say so in "
               "your assumptions.")
MAX_TURNS = 300
FORMAT_RETRIES = 2
# Proforma fields that describe the team and its aims. Institution and consent
# times are left out: the model does not need them.
CONTEXT_FIELDS = ("grade", "specialties", "specialtyUndecided", "topics", "publicationType",
                  "typeFlexibility", "topicFlexibility", "existingTitle", "hoursPerWeek",
                  "timeline", "statsConfidence", "databases", "supervisor", "collaborators",
                  "patientData", "nonEnglish", "anythingElse")

Say = Callable[[str], None]


class AgentError(RuntimeError):
    """A stage could not finish: the message says why and where its transcript is."""


# -- the prompt -------------------------------------------------------------------------
def load_prompt(path: Path, values: dict[str, Any]) -> str:
    """The system prompt from a stage's markdown file, every placeholder filled."""
    text = path.read_text(encoding="utf-8")
    # The marker on a line of its own: the notes above it quote the marker too.
    parts = re.split(rf"^{re.escape(MARKER)}[ \t]*$", text, maxsplit=1, flags=re.M)
    if len(parts) < 2:
        raise AgentError(f"{path} has no '{MARKER}' line: the prompt cannot be found in it.")
    body = parts[1].strip()
    missing: list[str] = []

    def fill(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            missing.append(key)
            return m.group(0)
        v = values[key]
        return v if isinstance(v, str) else json.dumps(v, indent=1, ensure_ascii=False)

    body = re.sub(r"\{\{\s*(\w+)\s*\}\}", fill, body)
    if missing:
        raise AgentError(f"{path.name} uses placeholders the pipeline does not fill: "
                         f"{', '.join(sorted(set(missing)))}")
    return body


def customer_context(proforma: dict) -> str:
    keep = {k: proforma[k] for k in CONTEXT_FIELDS if proforma.get(k) not in (None, "", [], {})}
    return json.dumps(keep, indent=1, ensure_ascii=False) if keep else "No details given."


def candidate_entry(review: Paper, flagged: str) -> dict:
    return {"candidate_id": review.pmid, "title": review.title,
            "authors": list(review.authors[:6]) + (["et al."] if len(review.authors) > 6 else []),
            "journal": review.journal, "year": review.first_published_year or review.year,
            "pmid": review.pmid, "doi": review.doi or "", "abstract": review.abstract,
            "search_end": "not known: the full text has not been read yet",
            "flagged_because": flagged}


# -- tools ------------------------------------------------------------------------------
TOOLS: list[dict] = [
    {"name": "pubmed_search",
     "description": "Search PubMed with full PubMed syntax (MeSH, [tiab], Boolean). Returns "
                    "the total hit count and up to 200 PMIDs. date_from and date_to are "
                    "publication dates as YYYY, YYYY/MM or YYYY/MM/DD, both optional.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "date_from": {"type": "string"},
         "date_to": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
     "eager_input_streaming": True},
    {"name": "pubmed_fetch",
     "description": f"Read up to {MAX_FETCH} PubMed records: title, abstract, publication "
                    f"types, year, journal. Abstracts over {ABSTRACT_CHARS} characters are "
                    "shortened and marked as such.",
     "input_schema": {"type": "object", "properties": {
         "pmids": {"type": "array", "items": {"type": "string"}}},
         "required": ["pmids"], "additionalProperties": False},
     "eager_input_streaming": True},
    {"name": "registry_search",
     "description": "Search Symposed's local copies of PROSPERO and OSF registrations by "
                    "title words. Use this, never web_search or web_fetch, for PROSPERO and "
                    "OSF: the web tools cannot reach either site. Returns each registration's "
                    "ID, title, date, link and (PROSPERO) title similarity from 0 to 1.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"], "additionalProperties": False},
     "eager_input_streaming": True},
    {"name": "db_lookup",
     "description": "Earlier Symposed assessments (Step 3b and Step 5b records) matching a "
                    "PMID or title words. Every word must match.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"], "additionalProperties": False},
     "eager_input_streaming": True},
]


def server_tools() -> list[dict]:
    return [{"type": "web_search_20260209", "name": "web_search",
             "blocked_domains": REGISTRY_DOMAINS},
            {"type": "web_fetch_20260209", "name": "web_fetch",
             "blocked_domains": REGISTRY_DOMAINS}]


def _norm_query(q: str) -> str:
    return " ".join(str(q).lower().split())


def _date(value: str, *, end: bool) -> Optional[str]:
    v = (value or "").strip().replace("-", "/")
    if not v:
        return None
    parts = v.split("/")
    if not all(p.isdigit() for p in parts) or not 1 <= len(parts) <= 3 or len(parts[0]) != 4:
        raise ValueError(f"not a date: {value!r} (use YYYY, YYYY/MM or YYYY/MM/DD)")
    if len(parts) == 1:
        parts += ["12", "31"] if end else ["01", "01"]
    elif len(parts) == 2:
        parts.append("31" if end else "01")
    return "/".join(parts)


@dataclass
class ToolLog:
    """What the tools really returned: the ground truth for Rule 1 checks."""

    searches: list[dict] = field(default_factory=list)
    pmids_seen: set[str] = field(default_factory=set)
    urls_seen: set[str] = field(default_factory=set)
    registry_ids: set[str] = field(default_factory=set)
    client_calls: int = 0
    web_searches: int = 0
    web_fetches: int = 0

    @property
    def calls(self) -> int:
        return self.client_calls + self.web_searches + self.web_fetches

    def find_search(self, query: str) -> Optional[dict]:
        q = _norm_query(query)
        hits = [s for s in self.searches if _norm_query(s["query"]) == q]
        return hits[-1] if hits else None


@dataclass
class AgentTools:
    pubmed: Any
    store: Any = None
    prospero: Any = None   # prospero.ProsperoMirror, None in testing runs
    osf: Any = None        # osf.OsfMirror
    log: ToolLog = field(default_factory=ToolLog)

    def run(self, name: str, args: Any) -> tuple[str, bool]:
        """(result text, is_error) for one client tool call."""
        self.log.client_calls += 1
        if not isinstance(args, dict):
            return "INVALID_JSON: the tool input was not a JSON object.", True
        try:
            if name == "pubmed_search":
                return json.dumps(self._search(args), ensure_ascii=False), False
            if name == "pubmed_fetch":
                return json.dumps(self._fetch(args), ensure_ascii=False), False
            if name == "registry_search":
                return json.dumps(self._registries(args), ensure_ascii=False), False
            if name == "db_lookup":
                return json.dumps(self._lookup(args), ensure_ascii=False, default=str), False
            return f"Unknown tool {name!r}.", True
        except ValueError as exc:
            return f"Invalid input: {exc}", True
        except httpx.HTTPError as exc:
            return f"PubMed request failed: {exc}", True

    def _search(self, args: dict) -> dict:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non empty string")
        mindate = _date(str(args.get("date_from") or ""), end=False)
        maxdate = _date(str(args.get("date_to") or ""), end=True)
        n, ids = self.pubmed.search_dated(query, datetype="pdat", mindate=mindate,
                                          maxdate=maxdate, retmax=MAX_PMIDS_RETURNED,
                                          store=False)
        self.log.searches.append({"query": query, "date_from": mindate, "date_to": maxdate,
                                  "hits": n})
        self.log.pmids_seen.update(ids)
        out = {"query": query, "date_from": mindate, "date_to": maxdate, "hits": n,
               "pmids": ids}
        if n > len(ids):
            out["note"] = f"Showing {len(ids)} of {n} PMIDs."
        return out

    def _fetch(self, args: dict) -> list[dict]:
        pmids = args.get("pmids")
        if not isinstance(pmids, list) or not pmids:
            raise ValueError("pmids must be a non empty list")
        pmids = [str(p).strip() for p in pmids if str(p).strip().isdigit()]
        if len(pmids) > MAX_FETCH:
            raise ValueError(f"at most {MAX_FETCH} PMIDs per call, got {len(pmids)}")
        out = []
        for p in self.pubmed.fetch_details(pmids, store=False):
            self.log.pmids_seen.add(p.pmid)
            abstract = p.abstract or ""
            if len(abstract) > ABSTRACT_CHARS:
                abstract = abstract[:ABSTRACT_CHARS] + " [abstract shortened]"
            out.append({"pmid": p.pmid, "year": p.first_published_year or p.year,
                        "title": p.title, "journal": p.journal,
                        "publication_types": list(p.publication_types), "abstract": abstract})
        return out

    def _registries(self, args: dict) -> Any:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non empty string")
        if self.prospero is None and self.osf is None:
            return {"checked": False, "note": NOT_CHECKED}
        out: dict[str, Any] = {"checked": True, "query": query}
        if self.osf is None:
            out["note"] = ("OSF is not in use in this testing run (SKIP_OSF_MIRROR=true): only "
                           "PROSPERO was searched. Say so in your assumptions.")
        if self.prospero is not None:
            out["prospero"] = [{"id": m.registration_id, "title": m.title,
                                "registered": str(m.registration_date or ""), "url": m.url,
                                "similarity": m.score}
                               for m in self.prospero.search(query, limit=REGISTRY_LIMIT)]
        if self.osf is not None:
            out["osf"] = [{"id": m.id, "title": m.title,
                           "registered": str(m.date_registered or ""), "url": m.link,
                           "template": m.registration_schema}
                          for m in self.osf.search(query, limit=REGISTRY_LIMIT)]
        for key in ("prospero", "osf"):
            for r in out.get(key, []):
                self.log.registry_ids.add(r["id"].lower())
                if r["url"]:
                    self.log.urls_seen.add(r["url"])
        return out

    def _lookup(self, args: dict) -> list[dict]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non empty string")
        if self.store is None:
            return []
        return self.store.lookup_triage(query)


# -- the loop -------------------------------------------------------------------------
@dataclass
class AgentResult:
    text: str                 # the model's last reply, summary and JSON
    summary: str              # the reply before <final_output>
    output: dict              # the parsed JSON
    log: ToolLog
    cost_usd: float
    turns: int
    models_used: list[str] = field(default_factory=list)  # more than one after a fallback


def fallback_params(setting: str) -> tuple[Optional[str], Any]:
    """(beta header, fallbacks value) for AGENT_REFUSAL_FALLBACK, or (None, None) when off."""
    setting = (setting or "").strip()
    if not setting or setting.lower() in ("off", "false", "no", "0"):
        return None, None
    if setting.lower() == "default":
        return FALLBACK_DEFAULT_BETA, "default"
    models = [m.strip() for m in setting.split(",") if m.strip()]
    return FALLBACK_LIST_BETA, [{"model": m} for m in models]


def after_fallback(content: list) -> list:
    """A reply to send back after a fallback: model-internal blocks from before the last
    fallback marker are dropped (thinking, tool calls), as the API requires."""
    idx = [i for i, b in enumerate(content) if _f(b, "type") == "fallback"]
    if not idx:
        return list(content)
    cut = idx[-1]
    keep_types = ("text", "server_tool_use", "web_search_tool_result", "web_fetch_tool_result")
    before = [b for b in content[:cut] if _f(b, "type") in keep_types]
    paired = {_f(b, "tool_use_id") for b in before if _f(b, "type", "").endswith("_tool_result")}
    before = [b for b in before if _f(b, "type") != "server_tool_use" or _f(b, "id") in paired]
    return before + list(content[cut:])


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    return str(obj)


def parse_final_output(text: str) -> tuple[str, dict]:
    m = re.search(r"<final_output>\s*(.*?)\s*</final_output>", text, re.S)
    if not m:
        raise ValueError("no <final_output> block")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", m.group(1).strip())
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("the <final_output> block is not a JSON object")
    return text[:m.start()].strip(), data


def _f(block: Any, key: str, default: Any = None) -> Any:
    """A field of a content block, whether an SDK object or a dict from a transcript."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _record_server_use(log: ToolLog, content: list) -> None:
    for b in content:
        t = _f(b, "type", "")
        if t == "server_tool_use":
            if _f(b, "name", "") == "web_search":
                log.web_searches += 1
            elif _f(b, "name", "") == "web_fetch":
                log.web_fetches += 1
                url = (_f(b, "input") or {}).get("url")
                if url:
                    log.urls_seen.add(url)
        elif t == "web_search_tool_result" and isinstance(_f(b, "content"), list):
            for r in _f(b, "content"):
                if _f(r, "url"):
                    log.urls_seen.add(_f(r, "url"))
        elif t == "web_fetch_tool_result":
            url = _f(_f(b, "content"), "url")
            if url:
                log.urls_seen.add(url)


def replay_log(messages: list[dict], log: ToolLog) -> None:
    """Rebuild what the tools returned from a saved conversation, so a resumed stage
    checks its reported counts and reviews against every search it ran."""
    calls: dict[str, tuple[str, Any]] = {}
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        if m.get("role") == "assistant":
            _record_server_use(log, content)
            for b in content:
                if _f(b, "type") == "tool_use":
                    calls[_f(b, "id")] = (_f(b, "name"), _f(b, "input") or {})
            continue
        for b in content:
            if _f(b, "type") != "tool_result" or _f(b, "tool_use_id") not in calls:
                continue
            text = _f(b, "content")
            if not isinstance(text, str) or text.startswith(BUDGET_TEXT[:40]):
                continue  # a budget refusal: the tool never ran
            log.client_calls += 1
            if _f(b, "is_error"):
                continue
            name, _ = calls[_f(b, "tool_use_id")]
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if name == "pubmed_search" and isinstance(data, dict):
                log.searches.append({k: data.get(k) for k in
                                     ("query", "date_from", "date_to", "hits")})
                log.pmids_seen.update(map(str, data.get("pmids", [])))
            elif name == "pubmed_fetch" and isinstance(data, list):
                log.pmids_seen.update(str(r.get("pmid")) for r in data if isinstance(r, dict))
            elif name == "registry_search" and isinstance(data, dict):
                for key in ("prospero", "osf"):
                    for r in data.get(key, []):
                        log.registry_ids.add(str(r.get("id", "")).lower())
                        if r.get("url"):
                            log.urls_seen.add(r["url"])


def load_resume(transcript: Path, system: str, model: str) -> Optional[dict]:
    """A stopped stage's saved conversation, if it can be continued: same prompt and
    model, so nothing it says was produced under different instructions."""
    if not transcript.exists():
        return None
    try:
        saved = json.loads(transcript.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if saved.get("system") != system or saved.get("model") != model:
        return None
    messages = list(saved.get("messages") or [])
    # A reply saved before declined replies were dropped (seen live 2026-10-30: a "bio"
    # decline left a thinking only turn, which the API refuses as a last block).
    def has_reply(content: Any) -> bool:
        if isinstance(content, str):
            return bool(content.strip())
        return any(_f(b, "type") in ("text", "tool_use", "server_tool_use")
                   for b in content or [])
    while messages and messages[-1].get("role") == "assistant" and not has_reply(
            messages[-1].get("content")):
        messages.pop()
    saved["messages"] = messages
    return saved if len(messages) > 1 else None


def run_agent(*, client: Any, model: str, effort: str, task: str, system: str,
              user_content: list[dict], tools: AgentTools, max_tool_calls: int,
              budget_usd: float, meter: Optional[UsageMeter], transcript: Path,
              say: Say = lambda _m: None, max_turns: int = MAX_TURNS,
              sleep: Callable[[float], None] = time.sleep,
              resume: Optional[dict] = None, fallback: str = "") -> AgentResult:
    """Run one stage to its final output. Never falls back to another model.

    `resume` (from load_resume) continues a stage that stopped part way, from its
    saved conversation: the turns already paid for are not repeated."""
    import anthropic

    meter = meter or UsageMeter()
    start_cost = meter.by_task.get(task, 0.0)
    messages: list[dict] = [{"role": "user", "content": user_content}]
    prior_cost = 0.0
    if resume:
        messages = list(resume["messages"])
        replay_log(messages, tools.log)
        prior_cost = float(resume.get("model_cost_usd") or 0.0)
        say(f"  {task}: resuming from {len(messages)} saved messages "
            f"({tools.log.calls} tool calls already made)")
    tool_defs = TOOLS + server_tools()
    fb_beta, fb_value = fallback_params(fallback)
    models_used: list[str] = []
    retries = turns = 0
    stopped = False

    def model_cost() -> float:
        return prior_cost + meter.by_task.get(task, 0.0) - start_cost

    def spent() -> float:
        return model_cost() + tools.log.web_searches * WEB_SEARCH_USD

    def save() -> None:
        transcript.write_text(json.dumps({"model": model, "system": system,
                                          "model_cost_usd": round(model_cost(), 4),
                                          "messages": messages}, default=_dump, indent=1,
                                         ensure_ascii=False), encoding="utf-8")

    while True:
        turns += 1
        if turns > max_turns:
            save()
            raise AgentError(f"{task} did not finish in {max_turns} turns (see {transcript}).")
        if spent() > budget_usd * 1.5:
            save()
            raise AgentError(f"{task} passed 1.5 times its ${budget_usd:.2f} budget without "
                             f"finishing (see {transcript}). Raise STAGE_BUDGET_USD to allow more.")
        params = dict(
            model=model, max_tokens=MAX_OUTPUT_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages, tools=tool_defs, thinking={"type": "adaptive"},
            output_config={"effort": effort}, betas=[CONTEXT_BETA] + ([fb_beta] if fb_beta else []),
            context_management={"edits": [CONTEXT_EDIT]},
            # Caches the conversation so far: each turn pays full price only for what is new.
            extra_body={"cache_control": {"type": "ephemeral"},
                        **({"fallbacks": fb_value} if fb_value else {})})
        response = None
        for attempt in range(CALL_RETRIES + 1):
            try:
                with client.beta.messages.stream(**params) as stream:
                    response = stream.get_final_message()
                break
            except anthropic.APIStatusError as exc:
                save()
                raise AgentError(f"{task}: the API call failed ({exc}). See {transcript}.") from exc
            except transport_errors() as exc:  # a dropped connection: send the turn again
                if attempt == CALL_RETRIES:
                    save()
                    raise AgentError(f"{task}: the connection failed {attempt + 1} times "
                                     f"({exc}). See {transcript}.") from exc
                say(f"  {task}: connection dropped, retrying ({attempt + 1}/{CALL_RETRIES})")
                sleep(RETRY_WAIT_SECONDS * 2 ** attempt)
        served = getattr(response, "model", None) or model
        if served not in models_used:
            models_used.append(served)
            if served != model:
                say(f"  {task}: a turn was declined and served by {served} instead")
        meter.record(served, task, response.usage)
        _record_server_use(tools.log, response.content)
        stop = response.stop_reason
        if stop not in ("refusal", "max_tokens"):  # a declined or cut off reply is never kept
            messages.append({"role": "assistant", "content": after_fallback(response.content)})
        if stop == "refusal":
            save()
            cat = getattr(getattr(response, "stop_details", None), "category", None)
            raise AgentError(f"{task}: the model declined ({cat}). See {transcript}.")
        if stop == "max_tokens":
            save()
            raise AgentError(f"{task}: a reply hit the {MAX_OUTPUT_TOKENS:,} token limit. "
                             f"See {transcript}.")
        if stop == "pause_turn":
            continue  # the server resumes its own tool loop from the paused turn
        if stop == "tool_use":
            over = tools.log.calls >= max_tool_calls or spent() >= budget_usd
            if over and not stopped:
                stopped = True
                say(f"  {task}: tool budget reached ({tools.log.calls} calls, "
                    f"${spent():.2f}), asking for the final output")
            results = []
            for b in response.content:
                if getattr(b, "type", "") != "tool_use":
                    continue
                if over:
                    text, err = BUDGET_TEXT, True
                else:
                    text, err = tools.run(b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": text,
                                **({"is_error": True} if err else {})})
            messages.append({"role": "user", "content": results})
            if turns % 10 == 0:
                say(f"  {task}: {tools.log.calls} tool calls so far, about ${spent():.2f}")
                save()
            continue
        text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        try:
            summary, output = parse_final_output(text)
        except (ValueError, json.JSONDecodeError) as exc:
            if retries >= FORMAT_RETRIES:
                save()
                raise AgentError(f"{task}: no valid <final_output> JSON after {retries + 1} "
                                 f"tries ({exc}). See {transcript}.") from exc
            retries += 1
            messages.append({"role": "user", "content": [{"type": "text", "text": (
                f"Your last reply had no valid JSON between <final_output> tags ({exc}). "
                "Reply again with the short summary and the complete JSON between the tags.")}]})
            continue
        save()
        return AgentResult(text, summary, output, tools.log, spent(), turns,
                           models_used or [model])


# -- Rule 1 checks ------------------------------------------------------------------------
def verify_output(output: Any, log: ToolLog) -> list[str]:
    """Mark every reported PubMed search and competing review as verified or not.

    A reported hit count that differs from what pubmed_search returned is
    replaced by the real count (the model's figure kept as hits_reported).
    """
    warnings: list[str] = []

    def check_search(s: dict) -> None:
        if "pubmed" not in str(s.get("source", "")).lower():
            s["verified"] = False
            return
        real = log.find_search(str(s.get("query", "")))
        if real is None:
            s["verified"] = False
            warnings.append(f"A PubMed search was reported but never run through the tool: "
                            f"{str(s.get('query', ''))[:120]}")
            return
        if s.get("hits") != real["hits"]:
            s["hits_reported"] = s.get("hits")
            s["hits"] = real["hits"]
            warnings.append(f"Hit count corrected from {s['hits_reported']} to {real['hits']} "
                            f"for: {real['query'][:120]}")
        s["verified"] = True

    def check_review(r: dict) -> None:
        ref = str(r.get("pmid_or_url", "")).strip()
        if ref.isdigit():
            r["verified"] = ref in log.pmids_seen
        elif ref.lower() in log.registry_ids:
            r["verified"] = True
        elif ref.startswith("http"):
            r["verified"] = any(ref.rstrip("/") == u.rstrip("/") for u in log.urls_seen)
        else:
            r["verified"] = False
        if not r["verified"]:
            warnings.append(f"Competing review not found in any tool result: "
                            f"{str(r.get('title', ''))[:100]} ({ref or 'no PMID or URL'})")

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            for s in o.get("searches", []) if isinstance(o.get("searches"), list) else []:
                if isinstance(s, dict):
                    check_search(s)
            crf = o.get("competing_reviews_found")
            for r in crf if isinstance(crf, list) else []:
                if isinstance(r, dict):
                    check_review(r)
            for k, v in o.items():
                if k not in ("searches", "competing_reviews_found"):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(output)
    return warnings


# -- the two stages -------------------------------------------------------------------
def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class StageRunner:
    """Runs Step 3b and Step 5b for one request, with the real API and tools."""

    settings: Any
    pubmed: Any
    store: Any = None
    client: Any = None
    meter: Optional[UsageMeter] = None
    prospero: Any = None   # the registry mirrors, None when SKIP_REGISTRY_MIRRORS=true
    osf: Any = None
    say: Say = lambda _m: None

    def __post_init__(self) -> None:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    def _params(self) -> dict:
        cfg = self.settings.updates
        return {"today": _today(), "target_eligible_min": cfg.target_eligible_min,
                "target_eligible_max": cfg.target_eligible_max,
                "max_calls_per_candidate": cfg.max_calls_per_candidate,
                "max_calls_per_option": cfg.max_calls_per_option,
                "full_screen_max": cfg.full_screen_max, "sample_size": cfg.sample_size}

    def _run(self, *, stage: int, task: str, prompt_file: str, values: dict,
             user_content: list[dict], max_tool_calls: int, folder: Path,
             candidate_ids: set[str]) -> dict:
        path = Path(self.settings.agent_prompts_dir) / prompt_file
        system = load_prompt(path, values)  # read fresh on every run
        tc = task_config(self.settings, task)
        self.say(f"  {task}: {tc.model}, effort {tc.effort}, prompt {path.name}")
        if self.prospero is not None:  # never search a stale copy (StaleMirrorError)
            self.prospero.ensure_fresh(max_age_days=self.settings.prospero_max_age_days)
        if self.osf is not None:
            self.osf.ensure_fresh(max_age_days=self.settings.mirror_staleness_days)
        tools = AgentTools(self.pubmed, self.store, self.prospero, self.osf)
        transcript = folder / f"stage{stage}_transcript.json"
        result = run_agent(client=self.client, model=tc.model, effort=tc.effort, task=task,
                           system=system, user_content=user_content, tools=tools,
                           max_tool_calls=max_tool_calls,
                           budget_usd=self.settings.updates.stage_budget_usd, meter=self.meter,
                           transcript=transcript, say=self.say,
                           resume=load_resume(transcript, system, tc.model),
                           fallback=self.settings.agent_refusal_fallback)
        warnings = verify_output(result.output, result.log)
        if result.models_used != [tc.model]:
            warnings.append(f"Some turns were served by {', '.join(m for m in result.models_used if m != tc.model)} "
                            f"after {tc.model} declined them (AGENT_REFUSAL_FALLBACK).")
        return {"stage": stage, "model": tc.model, "models_used": result.models_used,
                "prompt_file": str(path),
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "summary": result.summary, "output": result.output, "warnings": warnings,
                "tool_calls": {"pubmed_and_db": result.log.client_calls,
                               "web_search": result.log.web_searches,
                               "web_fetch": result.log.web_fetches},
                "cost_usd": round(result.cost_usd, 3), "turns": result.turns,
                "candidate_ids": sorted(candidate_ids)}

    def stage1(self, *, request: Any, reviews: list[tuple[Paper, str]],
               folder: Path) -> dict:
        """Shortlist five options from the candidate reviews (abstracts only)."""
        saved = folder / STAGE1_JSON
        if saved.exists():
            return json.loads(saved.read_text(encoding="utf-8"))
        ids = {p.pmid for p, _ in reviews}
        values = {**self._params(), "customer_context": customer_context(request.proforma),
                  "candidates": [candidate_entry(p, why) for p, why in reviews]}
        n = len(reviews)
        out = self._run(stage=1, task="stage1_triage", prompt_file=STAGE1_PROMPT, values=values,
                        user_content=[{"type": "text", "text": (
                            f"Assess the {n} candidate review{'s' if n != 1 else ''} and "
                            "select the top 5 options, following your instructions.")}],
                        max_tool_calls=self.settings.updates.max_calls_per_candidate * n,
                        folder=folder, candidate_ids=ids)
        top = out["output"].get("top_5") or []
        dropped = [t for t in top if str(t.get("candidate_id")) not in ids]
        if dropped:
            out["warnings"].append(f"{len(dropped)} shortlisted option(s) named a review that "
                                   "was not a candidate and were dropped.")
            out["output"]["top_5"] = [t for t in top if str(t.get("candidate_id")) in ids]
        self._store(1, folder, out)
        saved.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        write_stage1_md(folder / "STAGE1.md", out)
        return out

    def stage2(self, *, request: Any, stage1: dict, documents: list[tuple[Paper, str]],
               screening: Any, folder: Path) -> dict:
        """Read the shortlisted reviews' full texts and select one option."""
        saved = folder / STAGE2_JSON
        if saved.exists():
            return json.loads(saved.read_text(encoding="utf-8"))
        ids = {p.pmid for p, _ in documents}
        values = {**self._params(), "customer_context": customer_context(request.proforma),
                  "stage1_output": stage1["output"].get("top_5", []),
                  "screening_results": screening if screening else "not yet available"}
        content: list[dict] = [
            {"type": "document", "source": {"type": "text", "media_type": "text/plain",
                                            "data": text},
             "title": f"candidate_id {p.pmid}: {p.title}", "context": citation(p)}
            for p, text in documents]
        if content:
            content[-1]["cache_control"] = {"type": "ephemeral"}
        content.append({"type": "text", "text": (
            f"The full texts of the {len(documents)} shortlisted reviews are attached, each "
            "labelled with its candidate_id. Appraise them and select one option, following "
            "your instructions.")})
        out = self._run(stage=2, task="stage2_appraisal", prompt_file=STAGE2_PROMPT,
                        values=values, user_content=content,
                        max_tool_calls=self.settings.updates.max_calls_per_option
                        * max(1, len(documents)), folder=folder, candidate_ids=ids)
        sel = out["output"].get("selected") or {}
        if sel and str(sel.get("candidate_id")) not in ids:
            out["warnings"].append(f"The selected option names review {sel.get('candidate_id')}, "
                                   "whose full text was not supplied: it cannot be used.")
        self._store(2, folder, out)
        saved.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        write_stage2_md(folder / "STAGE2.md", out)
        return out

    def _store(self, stage: int, folder: Path, out: dict) -> None:
        if self.store is None:
            return
        o = out["output"]
        records: list[dict] = []
        if stage == 1:
            for t in o.get("top_5") or []:
                records.append({"candidate_id": t.get("candidate_id", ""),
                                "original_title": t.get("original_title", ""),
                                "option": t.get("angle_description") or t.get("option_type", ""),
                                "status": "shortlisted", "record": t})
            for r in o.get("database_records") or []:
                records.append({"candidate_id": r.get("candidate_id", ""),
                                "original_title": r.get("original_title", ""),
                                "option": r.get("option_tested", ""),
                                "status": r.get("status", ""), "record": r})
        else:
            sel = o.get("selected") or {}
            if sel:
                records.append({"candidate_id": sel.get("candidate_id", ""),
                                "original_title": sel.get("original_title", ""),
                                "option": sel.get("final_title", ""), "status": "selected",
                                "record": sel})
            for r in o.get("ranked_alternatives") or []:
                records.append({"candidate_id": r.get("candidate_id", ""),
                                "original_title": r.get("original_title", ""),
                                "option": r.get("best_option", ""), "status": "ranked",
                                "record": r})
            for r in o.get("database_records") or []:
                records.append({"candidate_id": r.get("candidate_id", ""),
                                "original_title": "", "option": r.get("option", ""),
                                "status": r.get("status", ""), "record": r})
        self.store.save_triage(stage, folder.name, records, model=out["model"])


# -- what a person reads --------------------------------------------------------------
def _range(e: Any) -> str:
    if isinstance(e, dict) and "low" in e and "high" in e:
        return f"{e['low']} to {e['high']} ({e.get('confidence', '?')} confidence)"
    return "not estimated"


def _scores(s: Any) -> str:
    if not isinstance(s, dict) or not s:
        return ""
    return ", ".join(f"{k} {v}" for k, v in s.items())


def _footer(out: dict) -> list[str]:
    lines = ["", f"Model {out['model']}, {out['turns']} turns, tool calls "
             f"{out['tool_calls']}, about ${out['cost_usd']:.2f}. Prompt: `{out['prompt_file']}`."]
    if out["warnings"]:
        lines += ["", "## Checks against the tool results (Rule 1)", ""]
        lines += [f"- {w}" for w in out["warnings"]]
    assumptions = out["output"].get("assumptions") or []
    if assumptions:
        lines += ["", "## The model's assumptions", ""] + [f"- {a}" for a in assumptions]
    return lines


def write_stage1_md(path: Path, out: dict) -> None:
    o = out["output"]
    lines = ["# Step 3b: triage shortlist", "", out["summary"], "",
             "| Rank | PMID | Option | Proposed title | Estimated eligible | Scores |",
             "|---|---|---|---|---|---|"]
    for t in o.get("top_5") or []:
        lines.append(f"| {t.get('rank', '')} | {t.get('candidate_id', '')} | "
                     f"{t.get('option_type', '')} | {t.get('proposed_title', '')} | "
                     f"{_range(t.get('estimated_eligible'))} | {_scores(t.get('scores'))} |")
    recs = o.get("database_records") or []
    if recs:
        lines += ["", "## Not shortlisted", ""]
        lines += [f"- {r.get('candidate_id', '')} ({r.get('status', '')}): "
                  f"{r.get('option_tested', '')}. {r.get('reason', '')}" for r in recs]
    path.write_text("\n".join(lines + _footer(out)) + "\n", encoding="utf-8")


def write_stage2_md(path: Path, out: dict) -> None:
    o = out["output"]
    sel = o.get("selected") or {}
    lines = ["# Step 5b: full text appraisal", "", out["summary"], ""]
    if sel:
        lines += [f"## Selected: {sel.get('final_title', '')}", "",
                  f"From PMID {sel.get('candidate_id', '')}, {sel.get('option_type', '')}. "
                  f"Estimated eligible {_range(sel.get('estimated_eligible'))}. "
                  f"Scores: {_scores(sel.get('scores'))}.", "",
                  str(sel.get("differs_from_original", "")), "",
                  "PubMed search:", "", "```", str((sel.get("search_strings") or {})
                                                   .get("pubmed", "")), "```"]
    alts = o.get("ranked_alternatives") or []
    if alts:
        lines += ["", "## Ranked alternatives", ""]
        lines += [f"{a.get('rank', '')}. PMID {a.get('candidate_id', '')}: "
                  f"{a.get('best_option', '')}. {a.get('why_not_selected', '')}" for a in alts]
    path.write_text("\n".join(lines + _footer(out)) + "\n", encoding="utf-8")
