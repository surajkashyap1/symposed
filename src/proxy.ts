import { NextResponse, type NextRequest, type NextResponse as NextResponseType } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";
import {
  REF_COOKIE,
  UTM_COOKIE,
  REF_COOKIE_MAX_AGE,
  normalizeCode,
} from "@/lib/attribution";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Channel attribution capture (Website Changes spec §9.1): record which link a
// visitor arrived through, into a first-touch 90-day cookie. The destination is
// unchanged, only the label is captured. First touch wins, so a later differing
// code is ignored. Visits are logged separately (the beacon route) and the code
// is written onto the user record at signup. Kept to cookies only, as the proxy
// runs at the network boundary with no database access.
function captureAttribution(request: NextRequest, response: NextResponseType) {
  const params = request.nextUrl.searchParams;

  const ref = normalizeCode(params.get("ref"));
  if (ref && !request.cookies.has(REF_COOKIE)) {
    response.cookies.set(REF_COOKIE, ref, {
      maxAge: REF_COOKIE_MAX_AGE,
      path: "/",
      sameSite: "lax",
    });
  }

  // Standard UTM parameters alongside the simple code, for whatever analytics
  // tool reads them. The simple code drives the administrator dashboard.
  const utm = [
    params.get("utm_source"),
    params.get("utm_medium"),
    params.get("utm_campaign"),
  ];
  if (utm.some(Boolean) && !request.cookies.has(UTM_COOKIE)) {
    response.cookies.set(UTM_COOKIE, utm.map((v) => v ?? "").join("|"), {
      maxAge: REF_COOKIE_MAX_AGE,
      path: "/",
      sameSite: "lax",
    });
  }
}

// Next 16 renamed `middleware` → `proxy`. This refreshes the Supabase session,
// protects routes (see src/lib/supabase/proxy.ts) and captures channel
// attribution.
export async function proxy(request: NextRequest) {
  // Malformed project ids get a real 404 here, before streaming locks the
  // status at 200 (loading.tsx). Valid-but-missing ids still stream a
  // noindex'd not-found page — checking existence would cost a DB roundtrip
  // on every project view. "new" is the static /projects/new route.
  const idSegment = request.nextUrl.pathname.match(/^\/projects\/([^/]+)/)?.[1];
  if (idSegment && idSegment !== "new" && !UUID_RE.test(idSegment)) {
    // Rewrite to an unrouted path: Next renders the not-found page with a
    // real 404 status because nothing streams first.
    const url = request.nextUrl.clone();
    url.pathname = "/404";
    return NextResponse.rewrite(url);
  }

  const response = await updateSession(request);
  captureAttribution(request, response);
  return response;
}

export const config = {
  // Run on all paths except static assets and image files.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
