"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { reviews, profiles } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { isUuid } from "@/lib/utils";
import { notify } from "@/lib/notify";
import { dimensionsFor, RATING_MIN, RATING_MAX } from "@/lib/review-meta";
import { getReviewableContext, recomputeReliability } from "@/lib/queries/reviews";
import { awardBadge, MENTOR_VALIDITY_MONTHS } from "@/lib/badges";

export async function submitReview(formData: FormData) {
  const user = await requireUser();
  const projectId = String(formData.get("projectId") ?? "");
  const revieweeId = String(formData.get("revieweeId") ?? "");
  if (!isUuid(projectId) || !isUuid(revieweeId)) redirect("/projects");

  const ctx = await getReviewableContext(projectId, user.id, revieweeId);
  if (!ctx) redirect(`/projects/${projectId}`);
  if (ctx.alreadyReviewed) redirect(`/profile/${revieweeId}`);

  const reviewUrl = `/projects/${projectId}/review/${revieweeId}`;
  const dims = dimensionsFor(ctx.direction);

  const row: typeof reviews.$inferInsert = {
    projectId,
    reviewerId: user.id,
    revieweeId,
    direction: ctx.direction,
    ratingOverall: "0",
    comment: String(formData.get("comment") ?? "").trim() || null,
    isAnonymous: formData.get("isAnonymous") === "on",
  };

  let sum = 0;
  for (const d of dims) {
    const v = parseInt(String(formData.get(d.key) ?? ""), 10);
    if (!Number.isFinite(v) || v < RATING_MIN || v > RATING_MAX) {
      redirect(`${reviewUrl}?error=${encodeURIComponent("Please rate every category from 1 to 5.")}`);
    }
    (row as Record<string, unknown>)[d.key] = v;
    sum += v;
  }
  row.ratingOverall = (sum / dims.length).toFixed(1);

  try {
    await db.insert(reviews).values(row);
  } catch {
    // Unique violation = already reviewed this pair for this project.
    redirect(`/profile/${revieweeId}`);
  }

  if (ctx.direction === "supervisor_to_member") {
    await recomputeReliability(revieweeId);
    // First completed review graduates the member from "New Researcher".
    await db
      .update(profiles)
      .set({ isNewResearcher: false })
      .where(eq(profiles.id, revieweeId));
    // Reviewing a member on a beginner-friendly project earns Research Mentor.
    if (ctx.isBeginnerFriendly) {
      const expires = new Date();
      expires.setMonth(expires.getMonth() + MENTOR_VALIDITY_MONTHS);
      await awardBadge(user.id, "research_mentor", expires);
    }
  }

  await notify({
    profileId: revieweeId,
    actorId: user.id,
    type: "review",
    title: "You received a review",
    body: `New review for your work on “${ctx.projectTitle}”.`,
    link: `/profile/${revieweeId}`,
  });

  revalidatePath(`/profile/${revieweeId}`);
  redirect(`/profile/${revieweeId}`);
}
