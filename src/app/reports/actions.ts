"use server";

import { redirect } from "next/navigation";
import { db } from "@/db";
import { reports } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

const TARGET_TYPES = new Set(["project", "question", "profile", "review"]);
const MAX_REASON_CHARS = 2000;

// Anyone signed in can report content or conduct (Safety Policy §2).
// Reports land on /admin for review and possible removal of the target.
export async function submitReport(formData: FormData) {
  const user = await requireUser();
  const targetType = String(formData.get("targetType") ?? "");
  const targetId = String(formData.get("targetId") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const backToRaw = String(formData.get("backTo") ?? "/projects");
  // Internal paths only, same rule as every redirect that round-trips a form.
  const backTo =
    backToRaw.startsWith("/") && !backToRaw.startsWith("//")
      ? backToRaw
      : "/projects";

  if (!TARGET_TYPES.has(targetType) || !isUuid(targetId)) redirect(backTo);
  if (!reason)
    redirect(`${backTo}?error=${encodeURIComponent("Please say why you're reporting this.")}`);

  await db.insert(reports).values({
    reporterId: user.id,
    targetType: targetType as "project" | "question" | "profile" | "review",
    targetId,
    reason: reason.slice(0, MAX_REASON_CHARS),
  });

  redirect(`${backTo}?reported=1`);
}
