import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { guideOrderFiles, guideOrders } from "@/db/schema";
import { getSessionUser } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { isUuid } from "@/lib/utils";

const GUIDE_BUCKET = "guide-files";

// Authenticated download route (spec §3.4): the account is the licence.
// A logged-out user or a different account gets 404 — never the file, and
// never a hint that the file exists.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ fileId: string }> }
) {
  const { fileId } = await params;
  if (!isUuid(fileId)) return new NextResponse(null, { status: 404 });

  const user = await getSessionUser();
  if (!user) return new NextResponse(null, { status: 404 });

  const [row] = await db
    .select({
      path: guideOrderFiles.path,
      filename: guideOrderFiles.filename,
      contentType: guideOrderFiles.contentType,
    })
    .from(guideOrderFiles)
    .innerJoin(guideOrders, eq(guideOrders.id, guideOrderFiles.orderId))
    .where(
      and(
        eq(guideOrderFiles.id, fileId),
        eq(guideOrders.profileId, user.id),
        eq(guideOrders.status, "delivered")
      )
    )
    .limit(1);
  if (!row) return new NextResponse(null, { status: 404 });

  // Stream through the app rather than redirecting to a signed URL, so no
  // shareable link ever exists.
  const admin = createAdminClient();
  const { data, error } = await admin.storage
    .from(GUIDE_BUCKET)
    .download(row.path);
  if (error || !data) return new NextResponse(null, { status: 404 });

  return new NextResponse(data.stream(), {
    headers: {
      "Content-Type": row.contentType,
      "Content-Disposition": `attachment; filename="${row.filename.replace(/"/g, "")}"`,
      "Cache-Control": "private, no-store",
    },
  });
}
