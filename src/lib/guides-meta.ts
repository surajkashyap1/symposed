// Shared copy + vocabulary for Publication Guides (docs spec §3).
// Shaded-box copy from the spec is used VERBATIM — several passages exist for
// legal reasons (Consumer Contracts Regulations, CRA 2015, DMCC Act 2024).
// Do not paraphrase or "improve" it.

export const GUIDE_GRADES = [
  "Medical student",
  "Foundation doctor",
  "Resident doctor / SHO",
  "Registrar",
  "Dental student",
  "Dentist",
  "Other",
] as const;

export const PUBLICATION_TYPES = [
  "Systematic review",
  "Literature review",
  "Narrative review",
  "Meta-analysis",
  "Case report",
  "Audit or QI write-up",
  "Not sure — recommend for me",
] as const;

export const HOURS_OPTIONS = ["Under 3", "3–5", "5–10", "Over 10"] as const;

export const TIMELINE_OPTIONS = [
  "Within 3 months",
  "3–6 months",
  "6–12 months",
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

export const MAX_GUIDE_SPECIALTIES = 3;
export const TOPIC_MAX_CHARS = 500;

// §3.1.1 — lead phrases bold, exactly as written.
export const WHAT_IS_INCLUDED: [string, string][] = [
  [
    "A verified research title.",
    "A specific question, checked against published systematic reviews, meta-analyses and registered protocols to confirm it has not already been answered.",
  ],
  [
    "A gap analysis.",
    "What has been published on your topic, what has not, and why your question is worth a journal's time.",
  ],
  [
    "A draft search strategy.",
    "Written in full Boolean syntax with MeSH terms, ready to paste into PubMed, Embase and Cochrane.",
  ],
  [
    "A draft protocol.",
    "Inclusion and exclusion criteria written for your specific question, not a generic template, with the reasoning behind each one.",
  ],
  [
    "A pre-populated PRISMA flow diagram.",
    "With the real record counts from the search we ran, ready to drop into your manuscript.",
  ],
  [
    "A data extraction template.",
    "The specific fields you will need for your review, as an editable spreadsheet.",
  ],
  [
    "A step-by-step method walkthrough.",
    "Screening, extraction, quality assessment and synthesis, written for your study design.",
  ],
  [
    "A shortlist of target journals.",
    "Matched to your study type and likely scope, with submission requirements and realistic acceptance expectations.",
  ],
  [
    "Who to approach for supervision.",
    "Named routes to support in your field, and a template for the approach email.",
  ],
  [
    "A disclosure statement.",
    "Wording you can copy into your methods and acknowledgements so your use of methodological support is properly declared to the journal.",
  ],
];

export const DELIVERY_PROMISE = "Your guide is delivered within 5 working days.";

// §3.1.4 — verbatim, deliberately generous, deliberately handles the
// ambiguous case.
export const GUARANTEE_PARAGRAPHS = [
  "If the review your guide is built around has already been published, we will refund you in full and produce a replacement guide on a different question at no cost.",
  "We check every question against published systematic reviews, meta-analyses and registered protocols before we build your guide. If you find a closely related publication that you believe overlaps with your question enough to count as duplication, email us within 30 days with the citation. Where the overlap is genuinely arguable, we will resolve it in your favour.",
];

// §3.1.2 — four steps, shown with icons.
export const HOW_IT_WORKS_STEPS: [string, string][] = [
  [
    "Tell us about your interests",
    "Complete a short proforma about your specialty, your topic and how much time you have.",
  ],
  [
    "We research the literature",
    "We search the published evidence and registered protocols to find a question that is genuinely open and genuinely doable.",
  ],
  [
    "You receive your guide within 5 working days",
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
    "No — that's the point of the guide. It also tells you exactly who to approach in your field when you do need one, with a template for the email.",
  ],
  [
    "Will this write my paper for me?",
    "No. It gives you a verified question and a full methodological foundation. You do the research.",
  ],
  [
    "Do I need to declare this to a journal?",
    "Yes, and we give you the wording. Most journals now require methodological and AI assistance to be disclosed — your guide includes a disclosure statement you can copy into your methods and acknowledgements.",
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
    "Yes — one guide, shared. Only one of you needs to buy it.",
  ],
  [
    "What is the refund policy?",
    "If your question turns out to have been already answered, you get a full refund and a free replacement guide — see the guarantee above. Full details are in our terms.",
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

// Launch mode: an introductory price of 0 renders as "Free" and checkout
// completes without Stripe.
export function formatPriceLabel(pence: number): string {
  return pence === 0 ? "Free" : formatPounds(pence);
}
