import { randomInt } from "node:crypto";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { verifications } from "@/db/schema";
import { sendEmail } from "@/lib/email";

const OTP_TTL_MS = 15 * 60 * 1000;

// Signup email confirmation via 6-digit OTP. The code is stored in the
// verifications table (type login_email) scoped to the profile, so a code is
// only ever checked against the signed-in account that requested it —
// guessing it confirms nothing you don't already control. Previous pending
// codes are invalidated on each send.
// Best-effort like everything email: returns whether an email actually went.
// When Resend isn't configured the caller may surface the code directly
// (dev/manual mode) so signup isn't blocked.
export async function sendSignupOtp(
  profileId: string,
  email: string
): Promise<{ sent: boolean; code: string }> {
  const code = String(randomInt(0, 1_000_000)).padStart(6, "0");

  await db
    .update(verifications)
    .set({ status: "rejected", token: null })
    .where(
      and(
        eq(verifications.profileId, profileId),
        eq(verifications.type, "login_email"),
        eq(verifications.status, "pending")
      )
    );
  await db.insert(verifications).values({
    profileId,
    type: "login_email",
    status: "pending",
    detail: email,
    token: code,
    expiresAt: new Date(Date.now() + OTP_TTL_MS),
  });

  const sent = await sendEmail({
    to: email,
    subject: `${code} is your Symposed confirmation code`,
    text: [
      `Welcome to Symposed!`,
      "",
      `Your confirmation code is: ${code}`,
      "",
      "Enter it on the confirmation page to finish creating your account. The code expires in 15 minutes.",
      "",
      "If you didn't sign up to Symposed, you can ignore this email.",
    ].join("\n"),
  });
  return { sent, code };
}

