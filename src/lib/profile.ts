import type { InferSelectModel } from "drizzle-orm";
import type { profiles } from "@/db/schema";

export type Profile = InferSelectModel<typeof profiles>;

// Word limits for free-text profile fields (kept in sync with the client
// counters in WordLimitedField). Enforced server-side in updateProfile.
export const SPECIALTY_WORD_LIMIT = 20;
export const SUMMARY_WORD_LIMIT = 50;

export function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

// Profile completeness (0–100) — drives the onboarding nudge (ROADMAP §1).
const COMPLETENESS_FIELDS: (keyof Profile)[] = [
  "fullName",
  "university",
  "specialty",
  "summary",
  "avatarUrl",
  "preferredProjectTypes",
  "preferredSpecialties",
];

export function computeCompleteness(p: Partial<Profile>): number {
  let filled = 0;
  for (const f of COMPLETENESS_FIELDS) {
    const v = p[f];
    if (typeof v === "string" && v.trim().length > 0) filled++;
  }
  if (
    typeof p.availabilityHoursPerWeek === "number" &&
    p.availabilityHoursPerWeek > 0
  ) {
    filled++;
  }
  // career stage chosen (not the default 'other') counts too
  if (p.careerStage && p.careerStage !== "other") filled++;
  const total = COMPLETENESS_FIELDS.length + 2;
  return Math.round((filled / total) * 100);
}

export function parseHoursPerWeek(value: FormDataEntryValue | null): number | null {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return null;
  return Math.min(80, Math.max(0, parsed));
}

// Optional contact phone. Kept private (never on a public profile), so we only
// normalise lightly: allow digits, spaces and the usual +()-. punctuation, trim
// to a sane length, and return null when effectively empty.
export function parseContactPhone(value: FormDataEntryValue | null): string | null {
  const cleaned = String(value ?? "")
    .replace(/[^\d+()\-\s]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 32);
  // Require at least a few digits to count as a real number.
  return (cleaned.match(/\d/g)?.length ?? 0) >= 5 ? cleaned : null;
}

export function parseListText(value: FormDataEntryValue | null): string | null {
  const items = String(value ?? "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (items.length === 0) return null;
  return Array.from(new Set(items)).join(", ");
}

export function parseSkillNames(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(/[\n,]/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
    .filter((item, index, all) => all.indexOf(item) === index)
    .slice(0, 20);
}

// Labels for the career_stage enum, grouped for the onboarding dropdown.
export const CAREER_STAGES: { value: Profile["careerStage"]; label: string }[] = [
  { value: "medical_student", label: "Medical student" },
  { value: "dental_student", label: "Dental student" },
  { value: "nursing_student", label: "Nursing student" },
  { value: "masters_student", label: "Master's student" },
  { value: "phd_student", label: "PhD student" },
  { value: "other_student", label: "Other student" },
  { value: "foundation_doctor", label: "Foundation doctor" },
  { value: "junior_doctor", label: "Junior doctor" },
  { value: "registrar", label: "Registrar" },
  { value: "consultant", label: "Consultant" },
  { value: "dentist", label: "Dentist" },
  { value: "qualified_nurse", label: "Nurse" },
  { value: "physician_associate", label: "Physician Associate" },
  { value: "advanced_clinical_practitioner", label: "Advanced Clinical Practitioner" },
  { value: "physiotherapist", label: "Physiotherapist" },
  { value: "pharmacist", label: "Pharmacist" },
  { value: "professor", label: "Professor" },
  { value: "postdoc", label: "Postdoctoral researcher" },
  { value: "staff_grade", label: "University staff grade" },
  { value: "other", label: "Other" },
];
