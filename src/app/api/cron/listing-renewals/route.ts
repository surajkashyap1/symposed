import { NextResponse } from "next/server";
import { and, eq, gt, isNull, lt, sql } from "drizzle-orm";
import { db } from "@/db";
import { availabilityListings, profiles } from "@/db/schema";
import { sendEmail } from "@/lib/email";

// Daily cron (vercel.json): emails owners of listings that expire within
// 7 days (i.e. around day 53 of 60) with a renewal prompt. Best-effort —
// expiry itself is enforced at query time, so a missed run only means a
// missed reminder, never a stale board.
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ ok: false }, { status: 401 });
    }
  }

  const expiring = await db
    .select({
      id: availabilityListings.id,
      email: profiles.email,
      name: profiles.fullName,
      expiresAt: availabilityListings.expiresAt,
    })
    .from(availabilityListings)
    .innerJoin(profiles, eq(profiles.id, availabilityListings.profileId))
    .where(
      and(
        eq(availabilityListings.status, "active"),
        gt(availabilityListings.expiresAt, sql`now()`),
        lt(availabilityListings.expiresAt, sql`now() + interval '7 days'`),
        isNull(availabilityListings.renewalEmailedAt)
      )
    );

  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  let sent = 0;
  for (const l of expiring) {
    const ok = await sendEmail({
      to: l.email,
      subject: "Your Symposed availability listing expires in a week",
      text: [
        `Hi ${l.name},`,
        "",
        `Your "Available for projects" listing expires on ${l.expiresAt.toLocaleDateString("en-GB")}.`,
        "Renewing takes one click and bumps you back to the top of the board:",
        "",
        `${base}/available`,
        "",
        "If you've found a project, you can mark that on the same page — it helps us know the board is working.",
      ].join("\n"),
    });
    if (ok) {
      await db
        .update(availabilityListings)
        .set({ renewalEmailedAt: new Date() })
        .where(eq(availabilityListings.id, l.id));
      sent += 1;
    }
  }

  return NextResponse.json({ ok: true, candidates: expiring.length, sent });
}
