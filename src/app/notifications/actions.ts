"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { and, eq, isNull } from "drizzle-orm";
import { db } from "@/db";
import { notifications } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

// Mark a single notification read when the user opens it, then follow its link.
// Scoped to the current user so you can't clear someone else's notification.
export async function markNotificationRead(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  const link = String(formData.get("link") ?? "");

  if (isUuid(id)) {
    await db
      .update(notifications)
      .set({ readAt: new Date() })
      .where(
        and(
          eq(notifications.id, id),
          eq(notifications.profileId, user.id),
          isNull(notifications.readAt)
        )
      );
    revalidatePath("/notifications");
    // SiteHeader lives in the root layout; refresh its unread badge.
    revalidatePath("/", "layout");
  }

  // The link round-trips through the form, so treat it as untrusted: follow
  // internal paths only ("//host" is a protocol-relative external URL).
  if (link.startsWith("/") && !link.startsWith("//")) redirect(link);
  redirect("/notifications");
}

export async function markAllNotificationsRead() {
  const user = await requireUser();
  await db
    .update(notifications)
    .set({ readAt: new Date() })
    .where(
      and(
        eq(notifications.profileId, user.id),
        isNull(notifications.readAt)
      )
    );
  revalidatePath("/notifications");
  revalidatePath("/", "layout");
}
