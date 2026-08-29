import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { teachingSubmissions } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { isUuid } from "@/lib/utils";

// Admin-only download of uploaded teaching material from the private bucket.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  await requireAdmin();
  const { id } = await params;
  if (!isUuid(id)) return new NextResponse(null, { status: 404 });

  const [s] = await db
    .select({
      path: teachingSubmissions.materialsPath,
      filename: teachingSubmissions.materialsFilename,
    })
    .from(teachingSubmissions)
    .where(eq(teachingSubmissions.id, id))
    .limit(1);
  if (!s) return new NextResponse(null, { status: 404 });

  const admin = createAdminClient();
  const { data, error } = await admin.storage
    .from("teaching-materials")
    .download(s.path);
  if (error || !data) return new NextResponse(null, { status: 404 });

  return new NextResponse(data.stream(), {
    headers: {
      "Content-Disposition": `attachment; filename="${s.filename.replace(/"/g, "")}"`,
      "Cache-Control": "private, no-store",
    },
  });
}
