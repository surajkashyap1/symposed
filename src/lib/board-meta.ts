// Shared vocabulary for the Available for Projects board (docs spec §5).

// Fixed list of offerable skills — a controlled vocabulary so the board's
// skill filter actually matches across listings.
export const SKILLS_OFFERED = [
  "Literature searching",
  "Title and abstract screening",
  "Full-text screening",
  "Data extraction",
  "Statistical analysis",
  "R",
  "SPSS",
  "Stata",
  "RevMan",
  "Manuscript writing",
  "Figure and table preparation",
  "Reference management",
  "Ethics applications",
  "REDCap",
  "Translation",
  "Illustration",
] as const;

export const SKILLS_OFFERED_SET = new Set<string>(SKILLS_OFFERED);

export const HEADLINE_MAX_CHARS = 80;
export const LOOKING_FOR_MAX_CHARS = 500;
export const MAX_LISTING_SPECIALTIES = 3;
export const LISTING_LIFETIME_DAYS = 60;
export const CONTACTS_PER_DAY = 10;
export const CONTACT_MAX_CHARS = 2000;

export function listingExpiryDate(from = new Date()): Date {
  return new Date(from.getTime() + LISTING_LIFETIME_DAYS * 24 * 60 * 60 * 1000);
}

// "Jane Smith" -> "J. S." for listings that prefer initials.
export function toInitials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "Anonymous";
  return parts.map((p) => `${p[0].toUpperCase()}.`).join(" ");
}

export function listingDisplayName(
  fullName: string,
  initialsOnly: boolean
): string {
  return initialsOnly ? toInitials(fullName) : fullName;
}
