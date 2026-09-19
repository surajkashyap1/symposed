import { NextResponse } from "next/server";
import { and, isNull, isNotNull, sql } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders } from "@/db/schema";
import { sendEmail } from "@/lib/email";

// Daily cron: alert the administrator when an order has been queued in paid /
// in-progress for more than 5 working days (amendment §3). Delivery is
// promised within 7 working days; alerting at more than 5 leaves a deliberate
// buffer, because promising 7 and delivering in 5 builds trust while missing 7
// silently destroys it. Alerts fire once per order (overdue_alerted_at).
export const dynamic = "force-dynamic";

function workingDaysSince(from: Date, to: Date): number {
  let days = 0;
  const cursor = new Date(from);
  while (cursor < to) {
    cursor.setDate(cursor.getDate() + 1);
    const dow = cursor.getDay();
    if (dow !== 0 && dow !== 6) days += 1;
  }
  return days;
}

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ ok: false }, { status: 401 });
    }
  }

  const candidates = await db
    .select()
    .from(guideOrders)
    .where(
      and(
        sql`${guideOrders.status} in ('paid', 'in_progress')`,
        isNotNull(guideOrders.paidAt),
        isNull(guideOrders.overdueAlertedAt)
      )
    );

  const now = new Date();
  const overdue = candidates.filter(
    (o) => o.paidAt && workingDaysSince(o.paidAt, now) > 5
  );

  const inbox =
    process.env.CONTACT_INBOX ??
    (process.env.ADMIN_EMAILS ?? "").split(",")[0]?.trim();
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";

  let alerted = 0;
  for (const o of overdue) {
    if (!inbox) break;
    const ok = await sendEmail({
      to: inbox,
      subject: `⚠ Guide order queued over 5 working days: ${o.fullName}`,
      text: [
        `Order ${o.id} (${o.fullName}, ${o.email}) was paid on ${o.paidAt!.toLocaleDateString("en-GB")} and is still ${o.status.replace("_", " ")}.`,
        "",
        "It has now been queued more than 5 working days. The 7-working-day delivery promise is approaching. Upload the guide today:",
        `${base}/admin`,
      ].join("\n"),
    });
    if (ok) {
      await db
        .update(guideOrders)
        .set({ overdueAlertedAt: new Date() })
        .where(sql`${guideOrders.id} = ${o.id}`);
      alerted += 1;
    }
  }

  return NextResponse.json({ ok: true, overdue: overdue.length, alerted });
}
