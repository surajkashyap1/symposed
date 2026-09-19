import { createHmac, timingSafeEqual } from "node:crypto";

// Amendment §8.5 — the listing-nudge emails carry an unsubscribe link that must
// work without logging in, and only for these specific nudges (separate from
// transactional email). We sign the profile id with a server secret so the
// link cannot be forged and no per-user token column is needed.

function secret(): string | null {
  return process.env.CRON_SECRET ?? process.env.STRIPE_WEBHOOK_SECRET ?? null;
}

export function signNudgeUnsubscribe(profileId: string): string | null {
  const s = secret();
  if (!s) return null;
  return createHmac("sha256", s).update(`nudge:${profileId}`).digest("hex");
}

export function verifyNudgeUnsubscribe(profileId: string, sig: string): boolean {
  const expected = signNudgeUnsubscribe(profileId);
  if (!expected) return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(sig);
  return a.length === b.length && timingSafeEqual(a, b);
}

// The absolute unsubscribe URL for an email (null when no secret is configured;
// callers then simply omit the link).
export function nudgeUnsubscribeUrl(base: string, profileId: string): string | null {
  const sig = signNudgeUnsubscribe(profileId);
  if (!sig) return null;
  return `${base}/nudges/unsubscribe?u=${profileId}&sig=${sig}`;
}
