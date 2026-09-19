"use server";

import { redirect } from "next/navigation";
import { db } from "@/db";
import { supportQuestions } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { getSupportState } from "@/lib/queries/member";

// Amendment §8.8 — a member with a live listing asks a bounded support
// question. The allowance is enforced here, not only in the form markup.
export async function askSupportQuestion(formData: FormData) {
  const user = await requireUser();
  const question = String(formData.get("question") ?? "").trim();

  const state = await getSupportState(user.id);
  if (!state.eligible)
    redirect(
      `/dashboard?support=${encodeURIComponent("Direct support is available once you have a live project listing.")}`
    );
  if (state.remaining <= 0)
    redirect(
      `/dashboard?support=${encodeURIComponent("You have used your support allowance. Contact us for more.")}`
    );
  if (question.length < 5)
    redirect(`/dashboard?support=${encodeURIComponent("Please write your question.")}`);

  await db.insert(supportQuestions).values({
    profileId: user.id,
    question: question.slice(0, 2000),
  });

  // Queue it to the admin inbox, batched with the weekly run.
  const inbox =
    process.env.CONTACT_INBOX ??
    (process.env.ADMIN_EMAILS ?? "").split(",")[0]?.trim();
  if (inbox) {
    await sendEmail({
      to: inbox,
      subject: `Support question from ${user.email ?? user.id}`,
      text: question,
    });
  }

  redirect("/dashboard?support=asked");
}
