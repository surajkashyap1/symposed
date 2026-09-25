// Shared copy + vocabulary for Publication Guides (docs spec §3, amended by
// the Website Changes spec). Shaded-box copy from the amendment is used
// VERBATIM: several passages exist for legal reasons (Consumer Contracts
// Regulations, CRA 2015, DMCC Act 2024). Do not paraphrase or "improve" it.
//
// House style (amendment §11): no em or en dashes in prose. Compound hyphens
// (pre-populated, non-English, follow-up) are kept. Ranges use the word "to".

export const GUIDE_GRADES = [
  "Medical student",
  "Foundation doctor",
  "Resident doctor / SHO",
  "Registrar",
  "Dental student",
  "Dentist",
  "Other",
] as const;

// Amendment §1: only review-type publications are offered. Exactly these four,
// in this order. Meta-analysis is treated as a systematic review with
// quantitative synthesis and has no separate option.
export const PUBLICATION_TYPES = [
  "Systematic review",
  "Literature review",
  "Narrative review",
  "Not sure, recommend one for me",
] as const;

// Guide request update (2026-09-25): we honour the review type and topic the
// user asks for, and only move away from either as far as they say they are
// flexible. Stored on the proforma; the pipeline reads them.
export const TYPE_FLEXIBILITY_OPTIONS = [
  "Only the type I chose",
  "Flexible, another review type is fine",
] as const;

export const TOPIC_FLEXIBILITY_OPTIONS = [
  "Only my stated topic",
  "Flexible within my specialty",
  "Fully flexible, any topic that suits my interests",
] as const;

// Shown on the request form, above the specialty and topic questions.
export const FLEXIBILITY_ADVICE =
  "Most specialty training programmes in the UK do not need your publication to be in a specific field. Please check your own programme's requirements before requesting a guide. Keeping your preferences flexible gives the best results, especially where your topic has already been well researched.";

// Shown on the request form and in the checkout pre-contract information.
export const EXACT_REQUIREMENTS_DISCLAIMER =
  "We can never promise a guide on a topic that matches your exact requirements. If we cannot find a suitable question within your preferences, we will email you to check whether you are flexible on anything before we go further.";

export const HOURS_OPTIONS = ["Under 3", "3 to 5", "5 to 10", "Over 10"] as const;

export const TIMELINE_OPTIONS = [
  "Within 3 months",
  "3 to 6 months",
  "6 to 12 months",
  "No deadline",
] as const;

export const STATS_OPTIONS = [
  "None",
  "Basic",
  "Comfortable with R / SPSS / Stata",
] as const;

export const DATABASE_OPTIONS = [
  "PubMed only",
  "Embase",
  "Cochrane Library",
  "Full institutional library access",
  "Unsure",
] as const;

export const SUPERVISOR_OPTIONS = ["Yes", "No", "Possibly"] as const;

export const YES_NO_OPTIONS = ["Yes", "No"] as const;

// Amendment §7.1: required, no zero option. Every project we design needs at
// least one collaborator.
export const COLLABORATOR_OPTIONS = ["1", "2", "3", "More than 3"] as const;

export const COLLABORATOR_HELP =
  "Every project we design is scoped for a small team. Reviews are stronger, and far more likely to be accepted, when papers are screened independently by more than one person.";

export const MAX_GUIDE_SPECIALTIES = 3;
export const TOPIC_MAX_CHARS = 500;

// Amendment §4.1 — hero description, word for word.
export const HERO_DESCRIPTION =
  "Tell us your publication requirements and we will search the literature to give you a project title and a complete guide on how to publish it.";

// Amendment §4.2 — method statement, word for word. The search method itself
// is proprietary and is never described in detail anywhere on the site (§4.3).
export const METHOD_STATEMENT =
  "We have developed and tested our own approach to finding research topics that can be published.";

// Amendment §5 — three "What is included" panels, shown laterally.
// Systematic review is first and is the default view. Each item is [lead,
// explanation]: the lead is bold, the explanation normal weight (empty where
// none is given).
export type PanelItem = readonly [lead: string, rest: string];
export type GuidePanel = {
  key: string;
  title: string;
  items: readonly PanelItem[];
};

export const GUIDE_PANELS: readonly GuidePanel[] = [
  {
    key: "systematic",
    title: "Systematic review",
    items: [
      ["A verified research question", "checked against published reviews and registered protocols"],
      ["The date your question was checked", "so you know exactly how current the check is"],
      ["A summary of similar published work", "and how your question differs from each"],
      ["Multiple complete search strategies", "with every search term, and a recommendation on which to use"],
      ["Translated syntax", "for the databases you will need to search yourself"],
      ["A table of suggested papers", "with study design, sample size, and where each one may be useful"],
      ["A full protocol", "with inclusion and exclusion criteria, and the reasoning behind each"],
      ["A pre-drafted PROSPERO registration entry", "so you can register and claim your question quickly"],
      ["A PRISMA flow diagram", "pre-populated with the counts from our search"],
      ["The correct risk of bias tool", "for your study design"],
      ["A recommended screening platform", "and how to set it up"],
      ["A data extraction template", ""],
      ["The statistical tests you are likely to need", "and the skills required to run them"],
      ["A full publication structure", "with headings, subheadings, figures and tables"],
      ["A timeline", "mapped to the hours you have available"],
      ["Common reasons this type of review is rejected", ""],
    ],
  },
  {
    key: "literature",
    title: "Literature review",
    items: [
      ["A verified research question", "checked against what has already been published"],
      ["A summary of similar published work", "and how yours differs"],
      ["Complete search strategies", "with every search term, and a recommendation on which to use"],
      ["A table of suggested papers", "organised by theme"],
      ["A structured approach", "to selecting and appraising your sources"],
      ["A full publication structure", "with headings and subheadings"],
      ["Guidance on synthesising findings", "where a meta-analysis is not appropriate"],
      ["A shortlist of target journals", "with their requirements"],
      ["A timeline", "mapped to the hours you have available"],
    ],
  },
  {
    key: "narrative",
    title: "Narrative review",
    items: [
      ["A verified topic and a defensible angle", ""],
      ["What has already been written on the topic", "and where the space is"],
      ["A search approach", "for identifying the key literature"],
      ["A table of suggested papers", "with a suggested use for each"],
      ["A structure for your argument", "with headings and subheadings"],
      ["Guidance on maintaining balance", "and avoiding the common criticisms of this format"],
      ["A shortlist of target journals", "with their requirements"],
      ["A timeline", "mapped to the hours you have available"],
    ],
  },
] as const;

// Amendment §3 — turnaround is 7 working days. Guide requests are processed in
// weekly batches; 7 working days accommodates the wait plus verification and
// delivery.
export const DELIVERY_PROMISE = "Your guide is delivered within 7 working days.";

// Amendment §6 — the modified guide commitment, word for word. The refund
// guarantee is removed. The statutory-rights line is REQUIRED and must not be
// removed (CRA 2015). Never use "no refunds", "non-refundable" or
// "all sales final" anywhere on the site.
export const GUARANTEE_PARAGRAPHS = [
  "If you believe the question in your guide has already been published, contact us within 30 days with the citation. We will work with you to refine the title, the angle and the workflow, and issue you a modified guide at no cost.",
  "This does not affect your statutory rights.",
];

// Amendment §4.4 — disclosure inside the delivered guide. Two SEPARATE items,
// which must not be conflated.
//
// Item one: the acknowledgement wording the buyer copies into their
// manuscript. Names Symposed only.
export const ACKNOWLEDGEMENT_WORDING =
  "Methodological support for this study was provided by Symposed.";

// Item two: a note addressed to the buyer, NOT copied into their paper. Appears
// in the delivered document only and never on any public page.
export const AUTHOR_AI_NOTE =
  "Note for authors: AI assisted tools were used in developing the search strategy for this guide. Most journals now require any use of AI in the preparation of a manuscript, including methodology development, to be declared. Please check the disclosure policy of your target journal before you submit, and declare accordingly.";

// Amendment §8.2 — what a buyer gets if they list their project. Lead phrase
// bold, explanation normal weight. Shown on the guides page, in the delivered
// guide and on the confirmation page.
export const LISTING_BENEFITS: [string, string][] = [
  [
    "Lead the project rather than just complete it.",
    "Recruiting and coordinating a team is evidence you cannot generate working alone, and it is recorded on your Symposed profile.",
  ],
  [
    "Named on your listing.",
    "Your project is posted under your name, so collaborators know who they are joining.",
  ],
  [
    "Priority placement.",
    "Projects that came from a Symposed guide sit at the top of the board.",
  ],
  [
    "Direct support while you work.",
    "Ask us about your methodology, your screening decisions or your analysis.",
  ],
  [
    "Help finding a supervisor.",
    "We will point you toward suitable people in your field.",
  ],
  [
    "Draft approach emails.",
    "We will write the email to your prospective supervisor if you want one.",
  ],
  [
    "A curated list of contacts once your work is done,",
    "to help you get it published.",
  ],
  [
    "For licensed professionals,",
    "a curated list of journals with their specific requirements set out in your guide.",
  ],
  [
    "More application credits,",
    "so you can apply to more projects on the platform.",
  ],
];

// Amendment §8.7 — page copy making clear benefits follow from posting, without
// making it sound like a hurdle.
export const BENEFITS_AVAILABILITY_NOTE =
  "These become available once you have posted your project on Symposed. Post it, and we will be in touch.";

// §3.1.2 — four steps, shown with icons. Copy avoids implying that a person
// performs the literature searching manually (amendment §4.3 boundary).
export const HOW_IT_WORKS_STEPS: [string, string][] = [
  [
    "Tell us your requirements",
    "Complete a short proforma about your specialty, your topic and how much time you have.",
  ],
  [
    "We search the literature",
    "Using our own developed and tested approach, we find a question that is genuinely open and genuinely doable.",
  ],
  [
    "You receive your guide within 7 working days",
    "Everything above, built around your specific project.",
  ],
  [
    "You start",
    "Post your project on Symposed to find collaborators, and get to work.",
  ],
];

// §3.1.5 — required questions, short direct answers in site tone.
export const GUIDE_FAQ: [string, string][] = [
  [
    "Do I need a supervisor to start?",
    "No. That is the point of the guide. It also tells you exactly who to approach in your field when you do need one, with a template for the email.",
  ],
  [
    "Will this write my paper for me?",
    "No. It gives you a verified question and a full methodological foundation. You do the research.",
  ],
  [
    "Do I need to declare this to a journal?",
    "Yes, and we give you the wording. Most journals now require methodological and AI assistance to be disclosed. Your guide includes a disclosure statement you can copy into your methods and acknowledgements.",
  ],
  [
    "What if I have no research experience at all?",
    "The guide is written for exactly that case. Every step is walked through for your specific study design.",
  ],
  [
    "How long will the project itself take?",
    "Honestly: a systematic review is typically three to six months of part-time work. The guide removes the months people usually lose to finding a viable question.",
  ],
  [
    "Can I buy a guide with collaborators?",
    "Yes. One guide, shared. Only one of you needs to buy it.",
  ],
  [
    "What if the question turns out to be already published?",
    "Contact us within 30 days with the citation. We will work with you to refine the title, the angle and the workflow, and issue you a modified guide at no cost. This does not affect your statutory rights. See the commitment above.",
  ],
];

// Pre-contract information (spec §7.2): shown on the checkout page, not only
// in the terms. Env-overridable so the registered address can change without
// a deploy once the business registers.
export function traderInfo() {
  return {
    name: process.env.TRADER_NAME ?? "Symposed",
    address:
      process.env.TRADER_ADDRESS ??
      "Registered address available on request via the contact form",
    email: process.env.TRADER_EMAIL ?? "via the contact form at /contact",
  };
}

export function formatPounds(pence: number): string {
  return pence % 100 === 0
    ? `£${pence / 100}`
    : `£${(pence / 100).toFixed(2)}`;
}

// Launch mode: a price of 0 renders as "Free" and checkout completes without
// Stripe.
export function formatPriceLabel(pence: number): string {
  return pence === 0 ? "Free" : formatPounds(pence);
}
