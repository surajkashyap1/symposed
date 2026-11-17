// Open project guides: ready-made guides sold as they are (Samarth,
// 2026-11-17). Shared by the public page, the card and the admin section.

export const OPEN_GUIDES_EMAIL = "symposed.support@gmail.com";

export const OPEN_GUIDE_TYPES = [
  { value: "systematic_review", label: "Systematic review" },
  { value: "literature_review", label: "Literature review" },
] as const;

export type OpenGuideType = (typeof OPEN_GUIDE_TYPES)[number]["value"];

export const OPEN_GUIDE_TYPE_VALUES = new Set<string>(OPEN_GUIDE_TYPES.map((t) => t.value));

export function openGuideTypeLabel(value: string): string {
  return OPEN_GUIDE_TYPES.find((t) => t.value === value)?.label ?? value;
}

// The public title is always generic: the specialty and the review type,
// never the research question.
export function openGuideTitle(g: { specialty: string; reviewType: string }): string {
  return `${g.specialty} ${openGuideTypeLabel(g.reviewType).toLowerCase()}`;
}

// A mailto link with the reference and title already in the subject.
export function openGuideMailto(g: {
  reference: string;
  specialty: string;
  reviewType: string;
}): string {
  const subject = `Open project guide ${g.reference} (${openGuideTitle(g)})`;
  const body = [
    `Hello Symposed,`,
    ``,
    `I would like to buy open project guide ${g.reference} (${openGuideTitle(g)}).`,
    ``,
    `My name:`,
    `My grade or role:`,
  ].join("\n");
  return `mailto:${OPEN_GUIDES_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export const OPEN_GUIDE_DESCRIPTION_MAX = 400;
export const OPEN_GUIDE_SPECIALTY_MAX = 80;
