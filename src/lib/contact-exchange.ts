import { inArray } from "drizzle-orm";
import { db } from "@/db";
import { profiles } from "@/db/schema";
import { sendEmail } from "@/lib/email";

// Contact details are private: the account email is always present, phone is
// optional. They're never shown on a public profile — only revealed to the
// counterparty once an application is accepted (auto-reveal, both ways).

export type ContactCard = { email: string; phone: string | null };

// Human-readable contact block for emails / UI copy.
export function formatContact(c: ContactCard): string {
  const lines = [`Email: ${c.email}`];
  if (c.phone) lines.push(`Phone: ${c.phone}`);
  return lines.join("\n");
}

// Fire the "you can now get in touch" emails to both the lister and the newly
// accepted applicant, each containing the other's contact details. Best-effort:
// gated on Resend being configured (sendEmail is a no-op otherwise) and never
// throws into the acceptance action.
export async function sendContactExchangeEmails(opts: {
  projectTitle: string;
  listerId: string;
  applicantId: string;
}): Promise<void> {
  try {
    const rows = await db
      .select({
        id: profiles.id,
        name: profiles.fullName,
        email: profiles.email,
        phone: profiles.contactPhone,
      })
      .from(profiles)
      .where(inArray(profiles.id, [opts.listerId, opts.applicantId]));

    const lister = rows.find((r) => r.id === opts.listerId);
    const applicant = rows.find((r) => r.id === opts.applicantId);
    if (!lister?.email || !applicant?.email) return;

    const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
    const guidance =
      "They've been given your contact details too. Please use these only for " +
      "this collaboration, and never for anything else.";

    await Promise.all([
      sendEmail({
        to: applicant.email,
        subject: `You've been accepted to “${opts.projectTitle}”`,
        text:
          `Good news, you've been accepted to “${opts.projectTitle}” on Symposed.\n\n` +
          `You can now contact the project lister directly:\n\n` +
          `${formatContact({ email: lister.email, phone: lister.phone })}\n\n` +
          `${guidance}\n\n${base}/applications`,
      }),
      sendEmail({
        to: lister.email,
        subject: `You accepted ${applicant.name} for “${opts.projectTitle}”`,
        text:
          `You've accepted ${applicant.name} for “${opts.projectTitle}” on Symposed.\n\n` +
          `You can now contact them directly:\n\n` +
          `${formatContact({ email: applicant.email, phone: applicant.phone })}\n\n` +
          `${guidance}\n\n${base}/projects`,
      }),
    ]);
  } catch (e) {
    console.error("sendContactExchangeEmails failed", e);
  }
}
