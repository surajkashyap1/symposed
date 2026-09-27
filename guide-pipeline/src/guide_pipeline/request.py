"""A guide request, built from the website's proforma answers.

Maps the form's wording onto what the pipeline needs: the review type and how
flexible the user is on it, the topic (which may be blank) and how flexible they
are on it, their specialties, team size, and a short plain-language description
of the user so every candidate question is feasible for them. Proformas sent
before the flexibility questions existed default to the strict reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .candidates import TOPIC_ANY, TOPIC_EXACT, TOPIC_SPECIALTY, RequestPreferences
from .gates import SYSTEMATIC

NOT_SURE = "Not sure, recommend one for me"
PUBLICATION_TYPES = {
    "Systematic review": SYSTEMATIC,
    "Literature review": "literature review",
    "Narrative review": "narrative review",
    NOT_SURE: SYSTEMATIC,  # we recommend; start from the most demanding type
}
TYPE_FLEXIBLE = "Flexible, another review type is fine"
TOPIC_FLEXIBILITY = {
    "Only my stated topic": TOPIC_EXACT,
    "Flexible within my specialty": TOPIC_SPECIALTY,
    "Fully flexible, any topic that suits my interests": TOPIC_ANY,
}
# The form asks how many OTHER people they can involve; the team includes them.
OTHERS_TO_TEAM = {"1": 2, "2": 3, "3": 4, "More than 3": 5}


@dataclass(frozen=True)
class GuideRequest:
    order_id: str
    topic: str  # as the user wrote it; may be blank
    preferences: RequestPreferences
    proforma: dict

    @property
    def blank_topic(self) -> bool:
        return not self.topic.strip()

    @property
    def generation_topic(self) -> str:
        """What candidate generation is asked to work within."""
        if not self.blank_topic:
            return self.topic.strip()
        where = " or ".join(self.preferences.specialties)
        if where:
            return (
                f"No topic given: any open review question within {where} that suits "
                "the user"
            )
        return "No topic or specialty given: any open clinical review question that suits the user"

    @property
    def search_topic(self) -> str:
        """Plain terms for the landscape scan."""
        if not self.blank_topic:
            return self.topic.strip()
        return " OR ".join(self.preferences.specialties) or "clinical medicine"


def _user_context(p: dict[str, Any], team: int) -> str:
    parts = [
        f"a {p['grade']}" if p.get("grade") else "",
        f"{p['hoursPerWeek']} hours a week" if p.get("hoursPerWeek") else "",
        f"target timeline {p['timeline'].lower()}" if p.get("timeline") else "",
        f"statistics confidence: {p['statsConfidence'].lower()}" if p.get("statsConfidence") else "",
        f"a team of {team}",
        f"database access: {', '.join(p['databases'])}" if p.get("databases") else "",
        "cannot read non-English papers" if p.get("nonEnglish") == "No" else "",
    ]
    text = "The user is " + "; ".join(x for x in parts if x) + "."
    if p.get("anythingElse"):
        text += f" They added: {p['anythingElse']}"
    return text


def from_proforma(proforma: dict[str, Any], *, order_id: str = "") -> GuideRequest:
    p = proforma
    pub = PUBLICATION_TYPES.get(p.get("publicationType", ""), SYSTEMATIC)
    type_flexible = (
        p.get("publicationType") == NOT_SURE or p.get("typeFlexibility") == TYPE_FLEXIBLE
    )
    topic = str(p.get("topics") or "").strip()
    specialties = tuple(
        s for s in (p.get("specialties") or []) if s and s != "Undecided"
    )
    topic_flex = TOPIC_FLEXIBILITY.get(p.get("topicFlexibility", ""), TOPIC_EXACT)
    if not topic:
        # A blank topic is itself flexibility: widen at least to the specialty.
        topic_flex = TOPIC_ANY if not specialties or topic_flex == TOPIC_ANY else TOPIC_SPECIALTY
    team = OTHERS_TO_TEAM.get(str(p.get("collaborators", "")), 2)
    prefs = RequestPreferences(
        publication_type=pub,
        type_flexible=type_flexible,
        topic_flexibility=topic_flex,
        specialties=specialties,
        collaborators=team,
        context=_user_context(p, team),
    )
    return GuideRequest(order_id=order_id, topic=topic, preferences=prefs, proforma=p)
