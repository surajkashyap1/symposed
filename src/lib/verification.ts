// Email-domain based verification.
// Academic emails worldwide (*.ac.uk, *.ac.nz, *.edu, *.edu.au, …) verify a
// student/academic. Health-service emails (NHS for now) verify a healthcare
// professional and make them *eligible* to supervise (final supervisor status
// also depends on career stage, refined at onboarding — docs/ROADMAP.md §4).
// Symposed is a global product: the classifier is deliberately not UK-only.
// Anything unrecognised can still be verified manually via /contact.

export type EmailClass = {
  isVerified: boolean;
  canSupervise: boolean;
  kind: "university" | "nhs" | null;
};

// Global academic domain shapes: `something.edu`, `something.edu.<cc>`,
// `something.ac.<cc>` (covers .ac.uk, .ac.nz, .ac.in, .ac.jp, …).
const ACADEMIC_DOMAIN_RE = /(\.edu|\.edu\.[a-z]{2}|\.ac\.[a-z]{2,3})$/;

export function classifyEmail(email: string): EmailClass {
  const domain = (email.toLowerCase().trim().split("@")[1] ?? "");
  if (domain === "nhs.net" || domain.endsWith(".nhs.uk")) {
    return { isVerified: true, canSupervise: true, kind: "nhs" };
  }
  if (ACADEMIC_DOMAIN_RE.test(domain)) {
    return { isVerified: true, canSupervise: false, kind: "university" };
  }
  return { isVerified: false, canSupervise: false, kind: null };
}

// Domain check for the standalone "Get verified" flow, where a user who signed
// up with any email proves they hold a recognised academic / health-service
// address. Returns null for anything we can't auto-verify (use the contact
// route instead).
export function verifiableEmailKind(
  email: string
): "university" | "nhs" | null {
  return classifyEmail(email).kind;
}
