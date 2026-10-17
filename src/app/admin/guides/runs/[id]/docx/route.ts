import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { guideRuns } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { isUuid } from "@/lib/utils";

// Admin-only download of a pipeline run's draft guide (Stage 6 review). The
// reviewer edits this draft and delivers the final files through the existing
// Deliver form. Since guide v2 the column holds a zip of the PDF guide and its
// companion files (tracker, protocol, PROSPERO draft); older runs hold a .docx.
// Both are zip containers, so the PDF entry name tells them apart.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  await requireAdmin();
  const { id } = await params;
  if (!isUuid(id)) return new NextResponse(null, { status: 404 });

  const [run] = await db
    .select({ docx: guideRuns.guideDocx, title: guideRuns.title })
    .from(guideRuns)
    .where(eq(guideRuns.id, id))
    .limit(1);
  if (!run?.docx) return new NextResponse(null, { status: 404 });

  const name = (run.title ?? "draft-guide")
    .replace(/[^A-Za-z0-9 -]/g, "")
    .trim()
    .slice(0, 60)
    .replace(/\s+/g, "-");
  const bytes = new Uint8Array(run.docx);
  const isPack = Buffer.from(bytes).includes("guide.pdf");
  return new NextResponse(bytes, {
    headers: {
      "Content-Type": isPack
        ? "application/zip"
        : "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="${name || "draft-guide"}.${isPack ? "zip" : "docx"}"`,
      "Cache-Control": "private, no-store",
    },
  });
}
