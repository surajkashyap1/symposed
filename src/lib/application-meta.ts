import type { InferSelectModel } from "drizzle-orm";
import type { applications } from "@/db/schema";

export type Application = InferSelectModel<typeof applications>;
export type ApplicationStatus = Application["status"];

// Standardised application form (ROADMAP §3 / plan §7). Word limits keep
// applications focused and comparable across candidates.
export const WORD_LIMITS = {
  motivation: 200,
  suitability: 200,
  skillsSummary: 100,
} as const;

// Weekly rolling application window (amendment §8.9). The per-week limit now
// varies by member tier (standard 3 / project lister 6 / guide lister 9) and
// is resolved from platform_config via getEntitlements, recomputed from current
// state each time. See src/lib/queries/entitlements.ts and
// getApplicationAllowance.
export const APPLICATION_WINDOW_DAYS = 7;

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  pending: "Pending",
  shortlisted: "Shortlisted",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

// Tailwind classes for the status badge — never colour-only (label carries it).
export const STATUS_BADGE_CLASS: Record<ApplicationStatus, string> = {
  pending: "bg-secondary text-secondary-foreground",
  shortlisted: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  accepted: "border-transparent bg-success text-success-foreground",
  rejected: "bg-muted text-muted-foreground",
  withdrawn: "bg-muted text-muted-foreground",
};

export function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

// Server-side validation mirror of the client word counters.
export function validateApplication(input: {
  motivation: string;
  suitability: string;
  hoursPerWeek: number | null;
  skillsSummary: string;
}): string | null {
  const motivation = input.motivation.trim();
  const suitability = input.suitability.trim();
  const skillsSummary = input.skillsSummary.trim();

  if (!motivation) return "Tell the supervisor why you're interested.";
  if (!suitability) return "Tell the supervisor why you're suitable.";
  if (input.hoursPerWeek == null || input.hoursPerWeek <= 0)
    return "Tell the supervisor how many hours you can dedicate to the role per week.";
  if (input.hoursPerWeek > 80)
    return "Weekly hours must be 80 or fewer.";
  if (countWords(motivation) > WORD_LIMITS.motivation)
    return `Motivation must be ${WORD_LIMITS.motivation} words or fewer.`;
  if (countWords(suitability) > WORD_LIMITS.suitability)
    return `Suitability must be ${WORD_LIMITS.suitability} words or fewer.`;
  if (countWords(skillsSummary) > WORD_LIMITS.skillsSummary)
    return `Skills summary must be ${WORD_LIMITS.skillsSummary} words or fewer.`;
  return null;
}
