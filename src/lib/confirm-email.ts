import { db } from "@/db";
import { verifications } from "@/db/schema";
import { sendEmail } from "@/lib/email";

const CONFIRM_TTL_MS = 24 * 60 * 60 * 1000;

// Supabase autoconfirm is on (its built-in mailer is too rate-limited to gate
// signups), so we prove the login email works ourselves: token in the
// verifications table, link over Resend. Callers treat this as best-effort —
// without Resend configured nothing sends and the account works regardless.
export async function sendLoginEmailConfirmation(
  profileId: string,
  email: string,
  origin: string
): Promise<boolean> {
  if (!process.env.RESEND_API_KEY || !process.env.RESEND_FROM) return false;

  const token = crypto.randomUUID();
  await db.insert(verifications).values({
    profileId,
    type: "login_email",
    status: "pending",
    detail: email,
    token,
    expiresAt: new Date(Date.now() + CONFIRM_TTL_MS),
  });

  const link = `${origin}/auth/verify-email?token=${token}`;
  return sendEmail({
    to: email,
    subject: "Confirm your email on Symposed",
    text: `Welcome to Symposed! Confirm this email address so we can reach you about applications and projects:\n\n${link}\n\nThis link expires in 24 hours.`,
  });
}
