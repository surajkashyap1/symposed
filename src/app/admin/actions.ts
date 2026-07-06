"use server";

import { revalidatePath } from "next/cache";
import { notFound, redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { listingQuestions, projects, reports } from "@/db/schema";
import { requireUser, ensureProfile } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

// Same gate as the /admin page: ADMIN_EMAILS env var, 404 for anyone else.
async function requireAdmin() {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const admins = (process.env.ADMIN_EMAILS ?? "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!admins.includes(profile.email.toLowerCase())) notFound();
  return user;
}

// Moderation removals (Safety Policy §4). Unpublishing sets the project to
// draft: hidden from the public (drafts 404 for non-owners) but preserved
// for the owner and for any appeal.
export async function unpublishProject(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin");

  await db
    .update(projects)
    .set({ status: "draft", updatedAt: new Date() })
    .where(eq(projects.id, id));

  revalidatePath("/projects");
  revalidatePath(`/projects/${id}`);
  redirect("/admin");
}

export async function removeQuestion(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin");

  await db.delete(listingQuestions).where(eq(listingQuestions.id, id));
  redirect("/admin");
}

export async function resolveReport(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  const outcome = String(formData.get("outcome") ?? "");
  if (!isUuid(id) || !["actioned", "dismissed"].includes(outcome))
    redirect("/admin");

  await db
    .update(reports)
    .set({
      status: outcome as "actioned" | "dismissed",
      resolvedAt: new Date(),
    })
    .where(eq(reports.id, id));

  redirect("/admin");
}
