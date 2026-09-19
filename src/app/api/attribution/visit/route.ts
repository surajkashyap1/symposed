import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { db } from "@/db";
import { attributionVisits } from "@/db/schema";
import {
  REF_COOKIE,
  VISIT_COOKIE,
  REF_COOKIE_MAX_AGE,
  DIRECT,
  normalizeCode,
} from "@/lib/attribution";

// Logs one first-touch visit per new visitor (spec §9.2), so the top of the
// funnel can be reported per code. The beacon in the layout calls this once per
// browser (deduped client-side); we also set a server-side marker cookie so a
// browser logs at most one visit per 90-day window even if the beacon fires
// again. The code comes from the first-touch cookie set by the proxy; an
// absent code is recorded as "direct" and never errors.
export const dynamic = "force-dynamic";

export async function POST() {
  const jar = await cookies();

  if (jar.get(VISIT_COOKIE)) {
    return new NextResponse(null, { status: 204 });
  }

  const code = normalizeCode(jar.get(REF_COOKIE)?.value) ?? DIRECT;
  await db.insert(attributionVisits).values({ code });

  const res = new NextResponse(null, { status: 204 });
  res.cookies.set(VISIT_COOKIE, "1", {
    maxAge: REF_COOKIE_MAX_AGE,
    path: "/",
    sameSite: "lax",
  });
  return res;
}
