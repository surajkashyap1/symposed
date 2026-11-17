import { and, desc, eq, ilike } from "drizzle-orm";
import { db } from "@/db";
import { openGuides } from "@/db/schema";
import type { OpenGuideType } from "@/lib/open-guides-meta";

export type OpenGuide = typeof openGuides.$inferSelect;

// Postgres "undefined_table": the open_guides migration (0013) has not been
// applied to this database yet. The page then shows its empty state instead
// of failing.
function isMissingTable(e: unknown): boolean {
  for (let err = e as { code?: string; cause?: unknown } | undefined; err; err = err.cause as typeof err) {
    if (err.code === "42P01") return true;
  }
  return false;
}

export async function listAvailableOpenGuides(filters: {
  specialty?: string;
  type?: OpenGuideType;
}): Promise<OpenGuide[]> {
  const where = [eq(openGuides.isAvailable, true)];
  if (filters.specialty) where.push(ilike(openGuides.specialty, `%${filters.specialty}%`));
  if (filters.type) where.push(eq(openGuides.reviewType, filters.type));
  try {
    return await db
      .select()
      .from(openGuides)
      .where(and(...where))
      .orderBy(desc(openGuides.createdAt));
  } catch (e) {
    if (isMissingTable(e)) return [];
    throw e;
  }
}

// Admin: every listing, available first. `null` when the table is missing.
export async function listAllOpenGuides(): Promise<OpenGuide[] | null> {
  try {
    return await db
      .select()
      .from(openGuides)
      .orderBy(desc(openGuides.isAvailable), desc(openGuides.createdAt));
  } catch (e) {
    if (isMissingTable(e)) return null;
    throw e;
  }
}
