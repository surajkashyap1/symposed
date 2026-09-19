// Channel attribution (Website Changes spec §9). A referral code is appended to
// any link (symposed.org/guides?ref=manchester). We capture it on first visit
// into a first-touch cookie, and write it once onto the user record at signup.
// An unrecognised or missing code is recorded as "direct"; we never reject or
// error on one, and first touch always wins over a later differing code.

export const REF_COOKIE = "sym_ref";
export const UTM_COOKIE = "sym_utm";
// Server-side dedupe marker for visit logging, so one browser logs at most one
// visit per lifetime window regardless of how many pages it loads.
export const VISIT_COOKIE = "sym_visit";

// 90-day lifetime (§9.1): many visitors arrive, leave, and return directly
// days later, so the code must outlive the session.
export const REF_COOKIE_MAX_AGE = 90 * 24 * 60 * 60;

export const DIRECT = "direct";

// Codes are lowercase, alphanumeric with hyphens, and carry no personal data
// (§9.3). We normalise defensively so a mistyped or oddly-cased inbound code is
// stored in one canonical form rather than fragmenting the report.
export function normalizeCode(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const code = raw
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
  return code.length ? code : null;
}

// Validation for administrator-created codes (§9.3): same character set, and it
// must survive normalisation unchanged so the link the admin copies matches the
// code that gets stored.
export function isValidCode(raw: string): boolean {
  return normalizeCode(raw) === raw && raw.length > 0;
}
