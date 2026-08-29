"use server";

import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { guideReviews } from "@/db/schema";
import { getOrderByReviewToken } from "@/lib/queries/guides";
import { sendEmail } from "@/lib/email";
import { GUIDE_GRADES } from "@/lib/guides-meta";

const MIN_REVIEW_CHARS = 40;
const MAX_REVIEW_CHARS = 3000;

// Buyer review via single-use token (spec §3.5). Reviews are moderated as a
// spam filter only — never edited; approval/rejection happens on /admin.
export async function submitGuideReview(formData: FormData) {
  const token = String(formData.get("token") ?? "");
  const back = `/guides/review/${token}`;
  const fail = (msg: string): never =>
    redirect(`${back}?error=${encodeURIComponent(msg)}`);

  const order = await getOrderByReviewToken(token);
  if (!order || order.status !== "delivered") redirect("/guides");

  const [existing] = await db
    .select({ id: guideReviews.id })
    .from(guideReviews)
    .where(eq(guideReviews.orderId, order.id))
    .limit(1);
  if (existing) redirect(`${back}?done=1`);

  const rating = Number.parseInt(String(formData.get("rating") ?? ""), 10);
  const body = String(formData.get("body") ?? "").trim();
  const displayName = String(formData.get("displayName") ?? "").trim();
  const reviewerRole = String(formData.get("reviewerRole") ?? "");
  const showInstitution = formData.get("showInstitution") === "on";
  const institution = String(formData.get("institution") ?? "").trim();
  const guideTopic = String(formData.get("guideTopic") ?? "").trim() || null;

  if (!rating || rating < 1 || rating > 5) fail("Please pick a rating.");
  if (body.length < MIN_REVIEW_CHARS)
    fail(`Please write at least ${MIN_REVIEW_CHARS} characters.`);
  if (body.length > MAX_REVIEW_CHARS)
    fail(`Reviews are capped at ${MAX_REVIEW_CHARS} characters.`);
  if (!displayName) fail("Please give a display name.");
  if (!GUIDE_GRADES.includes(reviewerRole as (typeof GUIDE_GRADES)[number]))
    fail("Please choose your grade or role.");

  await db.insert(guideReviews).values({
    orderId: order.id,
    reviewerName: displayName,
    reviewerRole,
    reviewerInstitution: showInstitution && institution ? institution : null,
    rating,
    body,
    guideTopic,
    // Paid buyers are not complimentary; the flag is set by the administrator
    // only for admin-created reviews (spec §3.5).
    complimentaryGuide: false,
  });

  const inbox =
    process.env.CONTACT_INBOX ??
    (process.env.ADMIN_EMAILS ?? "").split(",")[0]?.trim();
  if (inbox) {
    await sendEmail({
      to: inbox,
      subject: `Guide review awaiting moderation (${rating}/5)`,
      text: `${displayName} (${reviewerRole}) reviewed their guide:\n\n${body}\n\nApprove or reject on /admin.`,
    });
  }

  redirect(`${back}?done=1`);
}

// Reviewers can request removal at any time (spec §3.5); with the token in
// hand the removal is immediate.
export async function requestGuideReviewRemoval(formData: FormData) {
  const token = String(formData.get("token") ?? "");
  const order = await getOrderByReviewToken(token);
  if (!order) redirect("/guides");

  await db
    .update(guideReviews)
    .set({ status: "removed", publishedAt: null })
    .where(eq(guideReviews.orderId, order.id));

  redirect(`/guides/review/${token}?removed=1`);
}
