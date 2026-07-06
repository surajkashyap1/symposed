import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Next 16 renamed `middleware` → `proxy`. This refreshes the Supabase session
// and protects routes (see src/lib/supabase/proxy.ts).
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

  return await updateSession(request);
}

export const config = {
  // Run on all paths except static assets and image files.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
