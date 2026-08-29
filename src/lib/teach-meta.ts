// Shared vocabulary for the Teaching platform (docs spec §4).

export const TEACHING_AUDIENCES = [
  "Medical students",
  "Foundation doctors",
  "Resident doctors",
  "Dental students",
  "Other",
] as const;

export const TEACHING_AUDIENCES_SET = new Set<string>(TEACHING_AUDIENCES);

export const DELIVERY_FORMATS = [
  {
    value: "live_with_recordings",
    label: "Live webinar series with recordings released afterwards",
  },
  { value: "live_only", label: "Live only" },
  { value: "recorded_only", label: "Recorded only" },
] as const;

export type DeliveryFormat = (typeof DELIVERY_FORMATS)[number]["value"];

export const TOPIC_STATUS_LABELS: Record<string, string> = {
  accepting_submissions: "Accepting submissions",
  under_review: "Under review",
  filled: "Filled",
};

export const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  submitted: "Submitted",
  under_review: "Under review",
  revisions_requested: "Revisions requested",
  approved: "Approved",
  clinician_verification: "Awaiting clinician verification",
  scheduled: "Scheduled",
  delivered: "Delivered",
  declined: "Declined",
};

export const MIN_OBJECTIVES = 3;
export const MAX_OBJECTIVES = 5;
export const DESCRIPTION_MAX_CHARS = 1000;
export const MATERIALS_MAX_BYTES = 50 * 1024 * 1024;
export const MATERIALS_ACCEPT = ".pdf,.pptx,.docx";
export const MATERIALS_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

// The published review rubric (spec §4.2: applicants must know the standard
// before investing time). Shown on /teach.
export const TEACHING_RUBRIC = [
  {
    criterion: "Clinical accuracy and safety",
    standard:
      "Content is correct, current, and safe. Sources or guidelines are named where it matters. This is pass/fail — everything else is negotiable, this is not.",
  },
  {
    criterion: "Clear learning objectives",
    standard:
      "3–5 objectives a learner could be assessed against, matched to the stated audience.",
  },
  {
    criterion: "Structure and pacing",
    standard:
      "A session plan that fits the format — one idea per session, realistic timings, active elements rather than an hour of slides.",
  },
  {
    criterion: "Audience fit",
    standard:
      "Pitched at the stated audience's level; assumes what they know, teaches what they don't.",
  },
  {
    criterion: "Deliverability",
    standard:
      "The proposer can realistically deliver the series: relevant experience, sensible schedule, materials that already exist in draft.",
  },
] as const;
