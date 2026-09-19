"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders, projects } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { isUuid } from "@/lib/utils";
import { detectSensitiveInfo, sensitiveInfoMessage } from "@/lib/sensitive-info";
import { createDraftForOrder } from "@/lib/guide-listing";

// Amendment §8.4 — the buyer manages the auto-created draft listing from My
// guides. Publishing is always an explicit action and never automatic.

function fail(msg: string): never {
  redirect(`/guides/mine?error=${encodeURIComponent(msg)}`);
}

async function ownDraft(userId: string, id: string) {
  const [row] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.id, id), eq(projects.ownerId, userId)))
    .limit(1);
  return row ?? null;
}

function parsePositions(raw: string): number {
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? Math.min(Math.max(n, 1), 50) : 1;
}

// Save edits to a draft (title, description, positions). Stays a draft.
export async function saveGuideDraft(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/guides/mine");
  const row = await ownDraft(user.id, id);
  if (!row || row.status !== "draft") redirect("/guides/mine");

  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const positions = parsePositions(String(formData.get("positionsAvailable") ?? "1"));
  if (!title || !description) fail("A listing needs a title and a description.");

  const findings = detectSensitiveInfo([title, description].join("\n"));
  if (findings.length > 0) fail(sensitiveInfoMessage(findings));

  await db
    .update(projects)
    .set({ title, description, positionsAvailable: positions, updatedAt: new Date() })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id), eq(projects.status, "draft")));
  redirect("/guides/mine?draftSaved=1");
}

// Publish the draft: an explicit, single-button action (§8.4). Flips the draft
// to a live, public listing on the board.
export async function publishGuideListing(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/guides/mine");
  const row = await ownDraft(user.id, id);
  if (!row) redirect("/guides/mine");
  if (row.status !== "draft") redirect(`/projects/${id}`);

  if (formData.get("noConfidentialInfo") !== "on")
    fail("Please confirm your listing contains no confidential or patient information.");

  const findings = detectSensitiveInfo([row.title, row.description].join("\n"));
  if (findings.length > 0) fail(sensitiveInfoMessage(findings));

  await db
    .update(projects)
    .set({ status: "open", updatedAt: new Date() })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id), eq(projects.status, "draft")));

  revalidatePath("/projects");
  redirect(`/projects/${id}?published=1`);
}

// Delete a draft. We offer to regenerate it from the guide rather than lose it
// permanently (§8.4), signalled by ?regenerate=<orderId>.
export async function deleteGuideDraft(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/guides/mine");
  const row = await ownDraft(user.id, id);
  if (!row || row.status !== "draft") redirect("/guides/mine");

  await db
    .delete(projects)
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id), eq(projects.status, "draft")));

  const back = row.sourceGuideOrderId
    ? `/guides/mine?regenerate=${row.sourceGuideOrderId}`
    : "/guides/mine";
  redirect(back);
}

// Regenerate a deleted draft from the original guide content (§8.4).
export async function regenerateGuideDraft(formData: FormData) {
  const user = await requireUser();
  const orderId = String(formData.get("orderId") ?? "");
  if (!isUuid(orderId)) redirect("/guides/mine");

  const [order] = await db
    .select()
    .from(guideOrders)
    .where(and(eq(guideOrders.id, orderId), eq(guideOrders.profileId, user.id)))
    .limit(1);
  if (!order || order.status !== "delivered") redirect("/guides/mine");

  await createDraftForOrder(order);
  redirect("/guides/mine?draftRegenerated=1");
}
