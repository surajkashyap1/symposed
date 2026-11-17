"use server";

import { randomInt } from "node:crypto";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { openGuides } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import {
  OPEN_GUIDE_DESCRIPTION_MAX,
  OPEN_GUIDE_SPECIALTY_MAX,
  OPEN_GUIDE_TYPE_VALUES,
  type OpenGuideType,
} from "@/lib/open-guides-meta";
import { isUuid } from "@/lib/utils";

function fail(msg: string): never {
  redirect(`/admin/open-guides?error=${encodeURIComponent(msg)}`);
}

// No 0/O or 1/I, so a reference read out or typed by a buyer is unambiguous.
const REF_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";

function newReference(): string {
  let code = "";
  for (let i = 0; i < 4; i++) code += REF_ALPHABET[randomInt(REF_ALPHABET.length)];
  return `OG-${code}`;
}

export async function createOpenGuide(formData: FormData) {
  await requireAdmin();
  const specialty = String(formData.get("specialty") ?? "").trim();
  const reviewType = String(formData.get("reviewType") ?? "");
  const description = String(formData.get("description") ?? "").trim();

  if (!specialty || specialty.length > OPEN_GUIDE_SPECIALTY_MAX)
    fail(`Give a specialty of up to ${OPEN_GUIDE_SPECIALTY_MAX} characters.`);
  if (!OPEN_GUIDE_TYPE_VALUES.has(reviewType)) fail("Choose the review type.");
  if (!description || description.length > OPEN_GUIDE_DESCRIPTION_MAX)
    fail(`Give a description of up to ${OPEN_GUIDE_DESCRIPTION_MAX} characters.`);

  // A clash on the unique reference is vanishingly rare: retry with a new one.
  for (let attempt = 0; attempt < 5; attempt++) {
    const inserted = await db
      .insert(openGuides)
      .values({
        reference: newReference(),
        specialty,
        reviewType: reviewType as OpenGuideType,
        description,
      })
      .onConflictDoNothing({ target: openGuides.reference })
      .returning({ id: openGuides.id });
    if (inserted.length) redirect("/admin/open-guides?added=1");
  }
  fail("Could not create a unique reference. Please try again.");
}

// Sold or withdrawn: off the public page, kept for the record.
export async function setOpenGuideAvailable(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/open-guides");
  await db
    .update(openGuides)
    .set({ isAvailable: formData.get("available") === "1", updatedAt: new Date() })
    .where(eq(openGuides.id, id));
  redirect("/admin/open-guides");
}

export async function deleteOpenGuide(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/open-guides");
  await db.delete(openGuides).where(eq(openGuides.id, id));
  redirect("/admin/open-guides");
}
