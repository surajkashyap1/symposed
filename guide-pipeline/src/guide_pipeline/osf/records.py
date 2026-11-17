"""OSF registrations: the record we keep, and which registrations we keep.

The mirror holds only registrations that look like a health systematic review
(or another evidence synthesis). OSF's API cannot filter by registration
template or registration date (checked live 2026-10-24: both are refused as
"not a filterable field"), so the harvest reads every public registration with
a sparse field set and applies the filter below locally.

Filter choices (spec: "inspect the registration schemas, select the systematic
review templates, plus a keyword and subject filter for health and medicine"):

1. Evidence synthesis. Of the 44 OSF registration templates, one is made for
   reviews: "Generalized Systematic Review Registration" (every version, matched
   by name). Many reviews are registered on general templates instead (OSF
   Preregistration, Open-Ended Registration), so a registration also counts when
   its title or description names a review design (`REVIEW_WORDS`).
2. Health. OSF subjects use the bepress taxonomy: anything under "Medicine and
   Health Sciences" counts, and so do health subjects filed elsewhere, such as
   "Clinical Psychology" (`HEALTH_SUBJECTS`). Many registrations carry no
   subject, so health words in the title or description count too
   (`HEALTH_WORDS`).

Both must hold. Recall comes first: a registration wrongly kept costs a row; one
wrongly dropped could let a duplicate through, so the word lists are broad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from ..prospero.records import clean_text, match_key

VIEW_URL = "https://osf.io/"

SR_TEMPLATES = ("generalized systematic review registration",)
REVIEW_WORDS = re.compile(
    r"systematic(ally)?\s+(literature\s+)?review|meta[\s-]?analy|meta[\s-]?synthes|"
    r"scoping\s+review|umbrella\s+review|rapid\s+review|overview\s+of\s+(systematic\s+)?reviews|"
    r"evidence\s+synthes|mapping\s+review|integrative\s+review|realist\s+(review|synthes)|"
    r"living\s+(systematic\s+)?review|network\s+meta|evidence\s+map|"
    r"literature\s+review|narrative\s+review|critical\s+review",
    re.IGNORECASE,
)
HEALTH_SUBJECTS = re.compile(
    r"medicine|health|nursing|pharmac|dentist|psychiatr|clinical\s+psychology|"
    r"neuroscience|nutrition|kinesiology|rehabilitation|epidemiolog|immunolog|"
    r"oncology|surgery|pediatric|paediatric|geriatric|physical\s+therapy|"
    r"occupational\s+therapy|speech\s+(and\s+)?language|toxicology|virology",
    re.IGNORECASE,
)
HEALTH_WORDS = re.compile(
    r"patient|clinic|health|disease|disorder|syndrome|therap|treatment|hospital|"
    r"nurs|surg|medic|cancer|tumou?r|diabet|cardi|stroke|mortality|morbidity|"
    r"infect|vaccin|pregnan|neonat|infant|child|adolescen|older\s+adults|elderly|"
    r"pain|depress|anxiety|psychiatr|mental|dementia|obes|nutrition|diet|"
    r"rehabilit|physiotherap|exercise|drug|pharmac|dental|oral\s+health|symptom|"
    r"diagnos|prognos|screening|injur|trauma|frailty|sepsis|asthma|copd|hiv|"
    r"covid|malaria|tubercul|kidney|renal|liver|hepat|epilep|parkinson|autis|adhd|"
    r"schizophren|psychos|psychot|bipolar|suicid|self[\s-]?harm|substance\s+use|alcohol|"
    r"smok|tobacco|addict|eating\s+disorder|anorexi|insomnia|sleep|well[\s-]?being|"
    r"wellbeing|arthrit|osteopor|fractur|allerg|dermat|ophthalm|glaucoma|hearing|"
    r"migraine|headache|hypertens|blood\s+pressure|cholesterol|anaemi|anemi|"
    r"maternal|birth|breastfeed|menopaus|fertil|contracept|disabilit|caregiv|"
    r"intensive\s+care|icu|emergency\s+department|primary\s+care|physician|doctor",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OsfRecord:
    id: str  # OSF GUID, e.g. "zrws4"
    title: str
    description: str = ""
    registration_schema: str = ""  # the template's name ("registration_supplement")
    date_registered: Optional[date] = None
    date_modified: Optional[datetime] = None
    subjects: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    withdrawn: bool = False

    @property
    def link(self) -> str:
        return VIEW_URL + self.id + "/"

    @property
    def normalised(self) -> str:
        """Text for matching: title and description, lower case, without
        stop and boilerplate words."""
        return match_key(f"{self.title} {self.description}")


def is_evidence_synthesis(r: OsfRecord) -> bool:
    if r.registration_schema.strip().lower() in SR_TEMPLATES:
        return True
    return bool(REVIEW_WORDS.search(r.title) or REVIEW_WORDS.search(r.description))


def is_health(r: OsfRecord) -> bool:
    if any(HEALTH_SUBJECTS.search(s) for s in r.subjects):
        return True
    return bool(HEALTH_WORDS.search(r.title) or HEALTH_WORDS.search(r.description))


def keep(r: OsfRecord) -> bool:
    """A health evidence synthesis: the registrations the mirror holds."""
    return is_evidence_synthesis(r) and is_health(r)


def _datetime(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_registration(item: dict) -> OsfRecord:
    """One registration from the API's JSON:API `data` list."""
    a = item.get("attributes") or {}
    subjects: list[str] = []
    for path in a.get("subjects") or []:  # a list of paths, each a list of {id, text}
        for s in path if isinstance(path, list) else [path]:
            text = (s or {}).get("text") if isinstance(s, dict) else None
            if text and text not in subjects:
                subjects.append(text)
    registered = _datetime(a.get("date_registered"))
    return OsfRecord(
        id=str(item["id"]),
        title=clean_text(a.get("title") or ""),
        description=clean_text(a.get("description") or ""),
        registration_schema=str(a.get("registration_supplement") or ""),
        date_registered=registered.date() if registered else None,
        date_modified=_datetime(a.get("date_modified")),
        subjects=tuple(subjects),
        tags=tuple(str(t) for t in a.get("tags") or []),
        withdrawn=bool(a.get("withdrawn")),
    )
