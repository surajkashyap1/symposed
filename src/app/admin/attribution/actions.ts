"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { db } from "@/db";
import { referralCodes } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { isValidCode, normalizeCode } from "@/lib/attribution";

// Administrators create codes without a deploy (spec §9.3). One distinct code
// per influencer, society or institution; never a shared code, since a shared
// one teaches nothing about which of them works. Codes are lowercase,
// alphanumeric with hyphens, and carry no personal data.
export async function createReferralCode(formData: FormData) {
  await requireAdmin();

  const raw = String(formData.get("code") ?? "").trim();
  const label = String(formData.get("label") ?? "").trim();
  const code = normalizeCode(raw);

  if (!code || !isValidCode(code)) {
    redirect(
      `/admin/attribution?error=${encodeURIComponent(
        "Code must be lowercase letters, numbers and hyphens only."
      )}`
    );
  }
  if (!label) {
    redirect(
      `/admin/attribution?error=${encodeURIComponent("Give the code a label.")}`
    );
  }

  await db.insert(referralCodes).values({ code, label }).onConflictDoNothing();
  revalidatePath("/admin/attribution");
  redirect("/admin/attribution");
}
