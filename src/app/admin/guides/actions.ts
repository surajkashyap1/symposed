"use server";

import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { guideOrderFiles, guideOrders, guidePricingConfig, guideReviews } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { createAdminClient } from "@/lib/supabase/admin";
import { isUuid } from "@/lib/utils";

const GUIDE_BUCKET = "guide-files";
const DELIVERY_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]);

function fail(msg: string): never {
  redirect(`/admin/guides?error=${encodeURIComponent(msg)}`);
}

export async function markOrderInProgress(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/guides");
  await db
    .update(guideOrders)
    .set({ status: "in_progress", updatedAt: new Date() })
    .where(eq(guideOrders.id, id));
  redirect("/admin/guides");
}

export async function markOrderRefunded(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/guides");
  // Money movement happens in the Stripe dashboard; this records the outcome
  // (and releases the discount slot, since only paid-family statuses hold one).
  await db
    .update(guideOrders)
    .set({ status: "refunded", updatedAt: new Date() })
    .where(eq(guideOrders.id, id));
  redirect("/admin/guides");
}

// One-click delivery (spec §3.4 / §6.4): upload the finished files against the
// order, record the human verification step (spec §7.5 — load-bearing), flip
// to delivered, and send the delivery + review emails.
export async function deliverOrder(formData: FormData) {
  const { profile } = await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/guides");

  const verifiedBy =
    String(formData.get("verifiedBy") ?? "").trim() || profile.fullName;
  const verificationNote = String(formData.get("verificationNote") ?? "").trim();
  if (!verificationNote)
    fail("Record what was checked or changed — it's the evidence that a person verified this guide.");

  const files = formData
    .getAll("files")
    .filter((f): f is File => f instanceof File && f.size > 0);
  if (files.length === 0) fail("Attach the guide files (PDF + DOCX + XLSX).");
  for (const f of files) {
    if (!DELIVERY_MIME_TYPES.has(f.type))
      fail(`"${f.name}" isn't a PDF, DOCX or XLSX file.`);
  }

  const [order] = await db
    .select()
    .from(guideOrders)
    .where(eq(guideOrders.id, id))
    .limit(1);
  if (!order) redirect("/admin/guides");
  if (order.status !== "paid" && order.status !== "in_progress")
    fail("Only paid orders can be delivered.");

  const admin = createAdminClient();
  for (const f of files) {
    const path = `${order.id}/${crypto.randomUUID()}-${f.name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-")}`;
    const { error } = await admin.storage
      .from(GUIDE_BUCKET)
      .upload(path, f, { contentType: f.type, upsert: false });
    if (error) fail(`Upload of "${f.name}" failed: ${error.message}`);
    await db.insert(guideOrderFiles).values({
      orderId: order.id,
      path,
      filename: f.name,
      contentType: f.type,
    });
  }

  const now = new Date();
  await db
    .update(guideOrders)
    .set({
      status: "delivered",
      deliveredAt: now,
      verifiedBy,
      verifiedAt: now,
      verificationNote,
      reviewRequestedAt: now,
      updatedAt: now,
    })
    .where(eq(guideOrders.id, order.id));

  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  await sendEmail({
    to: order.email,
    subject: "Your Symposed Publication Guide is ready",
    text: [
      `Hi ${order.fullName},`,
      "",
      "Your guide is ready. Download it from your account — your files stay available indefinitely:",
      `${base}/guides/mine`,
      "",
      "Your guide ends with a project ready to run. Post it on Symposed to recruit collaborators — screeners, extractors, a statistician:",
      `${base}/projects/new`,
      "",
      "If anything in the guide doesn't make sense, reply to this email.",
    ].join("\n"),
  });
  // Separate review request with the single-use token (spec §6.3).
  if (order.reviewToken) {
    await sendEmail({
      to: order.email,
      subject: "How was your guide? (2 minutes, honest words only)",
      text: [
        `Hi ${order.fullName},`,
        "",
        "If you have two minutes, a short review helps other students decide whether a guide is right for them. No login needed:",
        `${base}/guides/review/${order.reviewToken}`,
        "",
        "We publish reviews as written — good or bad — after a quick spam check, and you can remove yours at any time from the same link.",
      ].join("\n"),
    });
  }

  redirect("/admin/guides?delivered=1");
}

// Prices and quantity are administrator-configurable without a deploy
// (spec §3.1.3); prices entered in pounds, stored in pence, always totals.
export async function updateGuidePricing(formData: FormData) {
  await requireAdmin();
  const standard = Math.round(Number(formData.get("standardPounds")) * 100);
  const intro = Math.round(Number(formData.get("introPounds")) * 100);
  const quantity = Number.parseInt(String(formData.get("introQuantity") ?? ""), 10);
  const blocked = String(formData.get("blockedCountries") ?? "")
    .toUpperCase()
    .split(",")
    .map((c) => c.trim())
    .filter((c) => /^[A-Z]{2}$/.test(c));

  if (!Number.isFinite(standard) || standard <= 0 || !Number.isFinite(intro) || intro <= 0)
    fail("Prices must be positive amounts in pounds.");
  if (Number.isNaN(quantity) || quantity < 0)
    fail("The introductory quantity must be 0 or more.");

  await db
    .update(guidePricingConfig)
    .set({
      standardPricePence: standard,
      introPricePence: intro,
      introQuantity: quantity,
      blockedCountries: blocked,
      updatedAt: new Date(),
    })
    .where(eq(guidePricingConfig.id, 1));
  redirect("/admin/guides");
}

// Review moderation (spec §3.5): approval is a spam filter, not an editorial
// one — the body is never edited here.
export async function moderateGuideReview(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  if (!isUuid(id)) redirect("/admin/guides");

  if (decision === "approve") {
    await db
      .update(guideReviews)
      .set({ status: "approved", publishedAt: new Date() })
      .where(eq(guideReviews.id, id));
  } else if (decision === "reject") {
    await db
      .update(guideReviews)
      .set({ status: "rejected", publishedAt: null })
      .where(eq(guideReviews.id, id));
  } else if (decision === "toggle_complimentary") {
    const [r] = await db
      .select({ flag: guideReviews.complimentaryGuide })
      .from(guideReviews)
      .where(eq(guideReviews.id, id))
      .limit(1);
    if (r)
      await db
        .update(guideReviews)
        .set({ complimentaryGuide: !r.flag })
        .where(eq(guideReviews.id, id));
  }
  redirect("/admin/guides");
}

// Admin-created review for colleagues who received a free guide outside the
// payment flow — complimentary_guide is FORCED true (DMCC disclosure, §7.3),
// and the reviewer must have genuinely received and used a guide.
export async function createComplimentaryReview(formData: FormData) {
  await requireAdmin();
  const reviewerName = String(formData.get("reviewerName") ?? "").trim();
  const reviewerRole = String(formData.get("reviewerRole") ?? "").trim();
  const reviewerInstitution =
    String(formData.get("reviewerInstitution") ?? "").trim() || null;
  const rating = Number.parseInt(String(formData.get("rating") ?? ""), 10);
  const body = String(formData.get("body") ?? "").trim();
  const guideTopic = String(formData.get("guideTopic") ?? "").trim() || null;

  if (!reviewerName || !reviewerRole || !body || !rating || rating < 1 || rating > 5)
    fail("Complimentary reviews need a name, role, rating and the reviewer's own words.");

  await db.insert(guideReviews).values({
    orderId: null,
    reviewerName,
    reviewerRole,
    reviewerInstitution,
    rating,
    body,
    guideTopic,
    complimentaryGuide: true, // non-negotiable for admin-created reviews
    status: "pending",
  });
  redirect("/admin/guides");
}
