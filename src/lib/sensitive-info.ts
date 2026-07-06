// GDPR guard for public content: catches contact details and likely
// patient identifiers before they are published (project listings, public
// Q&A, public profile text). Server actions block on matches; the forms
// repeat the rules up front. Names can't be detected reliably by pattern —
// the form copy and Acceptable Use Policy carry that duty instead.

const EMAIL_RE = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i;

// UK numbers (07..., 01/02..., +44...) with optional spacing; requires the
// full 10-11 digit run so ordinary numbers in text don't trip it.
const PHONE_RE = /(?:\+44[\s-]?\(?0?\)?|\b0)(?:\d[\s-]?){9,10}\b/;

// dd/mm/yyyy or dd-mm-yyyy with a year old enough to look like a birth date
// rather than a deadline (deadlines are current/future years).
const DATE_LIKE_RE = /\b([0-3]?\d)[/\-.]([01]?\d)[/\-.](19\d{2}|20[0-2]\d)\b/g;
const DOB_CONTEXT_RE = /\b(dob|d\.o\.b|date of birth|born)\b/i;

// 10-digit runs, optionally 3-3-4 spaced, validated with the NHS mod-11
// check digit so phone fragments and reference numbers rarely match.
const NHS_CANDIDATE_RE = /\b\d{3}[ -]?\d{3}[ -]?\d{4}\b/g;

function isValidNhsNumber(digits: string): boolean {
  const d = digits.split("").map(Number);
  const sum = d.slice(0, 9).reduce((acc, n, i) => acc + n * (10 - i), 0);
  const check = 11 - (sum % 11);
  const expected = check === 11 ? 0 : check;
  return check !== 10 && d[9] === expected;
}

export type SensitiveFinding =
  | "an email address"
  | "a phone number"
  | "an NHS number"
  | "a date of birth";

export function detectSensitiveInfo(text: string): SensitiveFinding[] {
  const findings = new Set<SensitiveFinding>();

  if (EMAIL_RE.test(text)) findings.add("an email address");
  if (PHONE_RE.test(text)) findings.add("a phone number");

  for (const match of text.matchAll(NHS_CANDIDATE_RE)) {
    if (isValidNhsNumber(match[0].replace(/[ -]/g, ""))) {
      findings.add("an NHS number");
      break;
    }
  }

  const currentYear = new Date().getFullYear();
  for (const match of text.matchAll(DATE_LIKE_RE)) {
    const year = Number(match[3]);
    // Explicit DOB wording flags any date; otherwise only clearly-past
    // years (deadlines and project dates are current or future).
    if (DOB_CONTEXT_RE.test(text) || year <= currentYear - 10) {
      findings.add("a date of birth");
      break;
    }
  }

  return [...findings];
}

// Patient-identifier subset for private text (applications): contact
// details are allowed there per the Contact Sharing Policy, but patient
// data is never allowed anywhere.
export function detectPatientIdentifiers(text: string): SensitiveFinding[] {
  return detectSensitiveInfo(text).filter(
    (f) => f === "an NHS number" || f === "a date of birth"
  );
}

export function sensitiveInfoMessage(findings: SensitiveFinding[]): string {
  return `Your text appears to contain ${findings.join(
    " and "
  )}. To protect personal data (including patient data), contact details and personal identifiers can't be included in public content. See our Acceptable Use Policy.`;
}
