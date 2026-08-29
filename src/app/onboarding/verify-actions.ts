"use server";

import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { db } from "@/db";
import { verifications } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { verifiableEmailKind } from "@/lib/verification";

const VERIFY_TTL_MS = 24 * 60 * 60 * 1000;

// Start the "Get verified" flow: the user proves they hold a .ac.uk / .nhs.uk
// address (which may differ from their login email). We store a one-time token
// and email a confirmation link. Until Resend is configured the email can't be
// sent, so we hand the link straight back for manual verification.
export async function requestVerification(formData: FormData) {
  const user = await requireUser();
  const email = String(formData.get("verifyEmail") ?? "").trim().toLowerCase();

  const kind = verifiableEmailKind(email);
  if (!kind) {
    redirect(
      `/onboarding?verify=${encodeURIComponent(
        "Enter a university (.edu / .ac.xx) or NHS email address. For other institutional emails, contact us and we'll verify you manually."
      )}#verify`
    );
  }

  const token = crypto.randomUUID();
  await db.insert(verifications).values({
    profileId: user.id,
    type: kind === "university" ? "university_email" : "nhs_email",
    status: "pending",
    detail: email,
    token,
    expiresAt: new Date(Date.now() + VERIFY_TTL_MS),
  });

  const origin = (await headers()).get("origin") ?? process.env.NEXT_PUBLIC_SITE_URL ?? "";
  const link = `${origin}/auth/verify-email?token=${token}`;

  const sent = await sendEmail({
    to: email,
    subject: "Verify your account on Symposed",
    text: `Confirm this email to verify your account:\n\n${link}\n\nThis link expires in 24 hours. If you didn't request it, ignore this email.`,
  });

  if (sent) {
    redirect(`/onboarding?verify=sent#verify`);
  }
  // No email provider configured (zero-budget): surface the link directly.
  redirect(`/onboarding?verify=manual&link=${encodeURIComponent(link)}#verify`);
}
