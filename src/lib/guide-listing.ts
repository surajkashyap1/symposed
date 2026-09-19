import { and, desc, eq, ne, sql } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders, projects } from "@/db/schema";
import type { ProjectType } from "@/lib/project-meta";

// Amendment §8.4 — on guide delivery we automatically create a DRAFT project
// listing on the buyer's account, pre-populated from the guide/proforma, so
// posting is a single click rather than a form at the end of a long document.
// The draft is never auto-published (§8.4); publishing is always an explicit
// user action.

const LIVE_STATUSES = ["open", "in_progress", "completed"] as const;

// Map the guide's review type onto the closest project_type enum value.
function publicationToProjectType(pub: string | undefined): ProjectType {
  switch (pub) {
    case "Systematic review":
      return "systematic_review";
    case "Literature review":
    case "Narrative review":
      return "literature_review";
    default:
      return "other";
  }
}

function positionsFromCollaborators(value: string | undefined): number {
  if (value === "More than 3") return 4;
  const n = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(n) && n >= 1 ? Math.min(n, 50) : 1;
}

type Proforma = Record<string, unknown>;

// Build the draft project fields from an order's proforma. Every field is
// editable before publishing, so these are sensible starting points.
export function draftFromOrder(order: {
  id: string;
  proforma: string;
}): typeof projects.$inferInsert {
  let p: Proforma = {};
  try {
    p = JSON.parse(order.proforma) as Proforma;
  } catch {
    p = {};
  }

  const pub = typeof p.publicationType === "string" ? p.publicationType : undefined;
  const existingTitle =
    typeof p.existingTitle === "string" && p.existingTitle.trim()
      ? p.existingTitle.trim()
      : null;
  const topics = typeof p.topics === "string" ? p.topics.trim() : "";
  const specialties = Array.isArray(p.specialties)
    ? (p.specialties as string[]).filter((s) => s && s !== "Undecided")
    : [];
  const hours = typeof p.hoursPerWeek === "string" ? p.hoursPerWeek : "a few";
  const timeline = typeof p.timeline === "string" ? p.timeline : "a few months";

  const typeLabel = (pub ?? "review").toLowerCase();
  const topicShort = topics.length > 90 ? `${topics.slice(0, 90)}…` : topics;
  const title =
    existingTitle ??
    `${pub ?? "Review"}: ${topicShort || specialties[0] || "a verified research question"}`;

  const description = [
    `We are recruiting collaborators for a ${typeLabel} that came from a Symposed Publication Guide, so the research question is verified and the methodology is already mapped out.`,
    topicShort ? `Topic area: ${topicShort}` : "",
    `Expected time commitment: about ${hours} hours per week. Expected duration: ${timeline}.`,
    "Collaborators will screen independently, extract data and help write up. Please edit this description, the title and the details before you publish.",
  ]
    .filter(Boolean)
    .join("\n\n");

  return {
    ownerId: "", // filled by the caller
    title: title.slice(0, 200),
    description,
    projectType: publicationToProjectType(pub),
    experienceLevel: "beginner_welcome",
    specialty: specialties[0] ?? null,
    isBeginnerFriendly: true,
    positionsAvailable: positionsFromCollaborators(
      typeof p.collaborators === "string" ? p.collaborators : undefined
    ),
    status: "draft",
    sourceGuideOrderId: order.id,
  };
}

// The single listing (draft or published) tied to a guide order, if any.
export async function getListingForOrder(orderId: string) {
  const [row] = await db
    .select()
    .from(projects)
    .where(eq(projects.sourceGuideOrderId, orderId))
    .orderBy(desc(projects.createdAt))
    .limit(1);
  return row ?? null;
}

// True once a real (non-draft) listing has been published from this guide.
export async function hasPublishedListingFromOrder(orderId: string): Promise<boolean> {
  const [row] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(projects)
    .where(
      and(
        eq(projects.sourceGuideOrderId, orderId),
        ne(projects.status, "draft")
      )
    );
  return (row?.n ?? 0) > 0;
}

// Create the draft for a delivered order. Idempotent: if any listing already
// exists for the order (draft or published), returns it instead of duplicating.
export async function createDraftForOrder(order: {
  id: string;
  profileId: string;
  proforma: string;
}) {
  const existing = await getListingForOrder(order.id);
  if (existing) return existing;
  const values = draftFromOrder(order);
  values.ownerId = order.profileId;
  const [created] = await db.insert(projects).values(values).returning();
  return created;
}

export { LIVE_STATUSES };
