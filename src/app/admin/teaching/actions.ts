"use server";

import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { teachingSubmissions, teachingTopics } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { notify } from "@/lib/notify";
import { getProfile } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

function fail(msg: string): never {
  redirect(`/admin/teaching?error=${encodeURIComponent(msg)}`);
}

const DECISIONS = new Set([
  "under_review",
  "revisions_requested",
  "approved",
  "scheduled",
  "delivered",
  "declined",
]);

// Move a submission through the review pipeline (spec §4.2), emailing the
// applicant on outcomes. "Scheduled" (publication) is gated on recorded
// clinician confirmation — enforced here, not just in the UI.
export async function setTeachingStatus(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  const feedback = String(formData.get("feedback") ?? "").trim();
  if (!isUuid(id) || !DECISIONS.has(decision)) redirect("/admin/teaching");

  const [submission] = await db
    .select()
    .from(teachingSubmissions)
    .where(eq(teachingSubmissions.id, id))
    .limit(1);
  if (!submission) redirect("/admin/teaching");

  if (decision === "revisions_requested" && !feedback)
    fail("Revisions requested needs specific written feedback.");
  if (decision === "scheduled" && submission.clinicianStatus !== "confirmed")
    fail(
      "This course can't be scheduled: the approving clinician hasn't confirmed yet."
    );

  await db
    .update(teachingSubmissions)
    .set({
      status: decision as typeof submission.status,
      adminFeedback: feedback || submission.adminFeedback,
      updatedAt: new Date(),
    })
    .where(eq(teachingSubmissions.id, id));

  // Outcome notifications (spec §6.3).
  const applicant = await getProfile(submission.profileId);
  const messages: Record<string, [string, string]> = {
    approved: [
      "Your teaching proposal has been approved",
      `"${submission.title}" has been approved. We'll be in touch to schedule the series once your approving clinician has confirmed (if they haven't already).`,
    ],
    revisions_requested: [
      "Your teaching proposal needs revisions",
      `"${submission.title}" needs some changes before it can go ahead:\n\n${feedback}\n\nRevise and resubmit from the teaching page, your previous version is kept.`,
    ],
    declined: [
      "Your teaching proposal was declined",
      `Thanks for proposing "${submission.title}". We're not taking it forward${feedback ? `:\n\n${feedback}` : "."}`,
    ],
    scheduled: [
      "Your course is scheduled",
      `"${submission.title}" is confirmed and scheduled. We'll be in touch about dates and delivery.`,
    ],
  };
  const msg = messages[decision];
  if (msg && applicant) {
    await notify({
      profileId: applicant.id,
      type: "system",
      title: msg[0],
      body: undefined,
      link: "/teach",
    });
    await sendEmail({
      to: applicant.email,
      subject: `Symposed: ${msg[0].toLowerCase()}`,
      text: `Hi ${applicant.fullName},\n\n${msg[1]}\n\n${process.env.NEXT_PUBLIC_SITE_URL ?? ""}/teach`,
    });
  }

  redirect("/admin/teaching");
}

// Topic editor (spec §4.1.3): admin-configurable without a deploy.
export async function saveTeachingTopic(formData: FormData) {
  await requireAdmin();
  const idRaw = String(formData.get("id") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const format = String(formData.get("format") ?? "").trim();
  const deadlineRaw = String(formData.get("deadline") ?? "").trim();
  const status = String(formData.get("status") ?? "accepting_submissions");
  const sortOrder = Number.parseInt(String(formData.get("sortOrder") ?? "0"), 10) || 0;

  if (!title || !description || !format)
    fail("Topics need a title, description and format.");
  const values = {
    title,
    description,
    format,
    deadline: /^\d{4}-\d{2}-\d{2}$/.test(deadlineRaw) ? deadlineRaw : null,
    status: status as "accepting_submissions" | "under_review" | "filled",
    sortOrder,
  };

  const id = Number.parseInt(idRaw, 10);
  if (Number.isNaN(id)) {
    await db.insert(teachingTopics).values(values);
  } else {
    await db.update(teachingTopics).set(values).where(eq(teachingTopics.id, id));
  }
  redirect("/admin/teaching");
}
