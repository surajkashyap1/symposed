"use server";

import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { availabilityListings } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

// Moderation removal (reports land on /admin like every other target type).
export async function removeListingAdmin(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/admin/listings");
  await db
    .update(availabilityListings)
    .set({ status: "removed", updatedAt: new Date() })
    .where(eq(availabilityListings.id, id));
  redirect("/admin/listings");
}
