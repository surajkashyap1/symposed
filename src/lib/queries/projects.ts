import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import { db } from "@/db";
import { projects, profiles, applications } from "@/db/schema";
import type {
  ProjectType,
  ExperienceLevel,
} from "@/lib/project-meta";

// Correlated subquery: how many applications a project has (shown publicly).
const applicationCount = sql<number>`(
  select count(*)::int from ${applications}
  where ${applications.projectId} = ${projects.id}
)`.as("application_count");

const listColumns = {
  id: projects.id,
  ownerId: projects.ownerId,
  title: projects.title,
  description: projects.description,
  projectType: projects.projectType,
  experienceLevel: projects.experienceLevel,
  specialty: projects.specialty,
  roleCategory: projects.roleCategory,
  isBeginnerFriendly: projects.isBeginnerFriendly,
  positionsAvailable: projects.positionsAvailable,
  status: projects.status,
  applicationDeadline: projects.applicationDeadline,
  createdAt: projects.createdAt,
  ownerName: profiles.fullName,
  ownerUniversity: profiles.university,
  ownerCareerStage: profiles.careerStage,
  applicationCount,
};

export type ProjectListItem = {
  id: string;
  ownerId: string;
  title: string;
  description: string;
  projectType: ProjectType;
  experienceLevel: ExperienceLevel;
  specialty: string | null;
  roleCategory: string | null;
  isBeginnerFriendly: boolean;
  positionsAvailable: number;
  status: "draft" | "open" | "in_progress" | "closed" | "completed";
  applicationDeadline: string | null;
  createdAt: Date;
  ownerName: string | null;
  ownerUniversity: string | null;
  ownerCareerStage: string | null;
  applicationCount: number;
};

export type CompetitivenessRank = "beginner_first" | "competitive_first";

export type ListProjectsOptions = {
  q?: string;
  specialty?: string;
  type?: ProjectType;
  experience?: ExperienceLevel;
  rank?: CompetitivenessRank;
  page?: number;
};

export const PROJECTS_PAGE_SIZE = 6;

export type ProjectListPage = {
  items: ProjectListItem[];
  total: number;
  page: number;
  pageCount: number;
};

export async function listOpenProjects(
  opts: ListProjectsOptions
): Promise<ProjectListPage> {
  const conds = [eq(projects.status, "open")];

  if (opts.q) {
    conds.push(
      or(
        ilike(projects.title, `%${opts.q}%`),
        ilike(projects.description, `%${opts.q}%`)
      )!
    );
  }
  if (opts.specialty) {
    conds.push(ilike(projects.specialty, `%${opts.specialty}%`));
  }
  if (opts.type) conds.push(eq(projects.projectType, opts.type));
  if (opts.experience) conds.push(eq(projects.experienceLevel, opts.experience));

  const beginnerRank = sql<number>`case when ${projects.isBeginnerFriendly} or ${projects.experienceLevel} = 'beginner_welcome' then 1 else 0 end`;
  const competitiveRank = sql<number>`case when ${projects.experienceLevel} in ('some_experience', 'experienced_only') and ${projects.isBeginnerFriendly} = false then 1 else 0 end`;
  const rankOrder =
    opts.rank === "competitive_first"
      ? desc(competitiveRank)
      : desc(beginnerRank);

  // Count first so an out-of-range ?page= clamps to the last real page
  // instead of rendering an empty grid.
  const [{ total }] = await db
    .select({ total: sql<number>`count(*)::int` })
    .from(projects)
    .where(and(...conds));

  const pageCount = Math.max(1, Math.ceil(total / PROJECTS_PAGE_SIZE));
  const page = Math.min(Math.max(1, Math.floor(opts.page ?? 1)), pageCount);

  const items = await db
    .select(listColumns)
    .from(projects)
    .leftJoin(profiles, eq(profiles.id, projects.ownerId))
    // Beginner-friendly listings get higher visibility (ROADMAP §9/§11).
    .where(and(...conds))
    .orderBy(rankOrder, desc(projects.createdAt), desc(projects.id))
    .limit(PROJECTS_PAGE_SIZE)
    .offset((page - 1) * PROJECTS_PAGE_SIZE);

  return { items, total, page, pageCount };
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Full projects row (for the owner edit form).
export async function getProjectRow(id: string) {
  if (!UUID_RE.test(id)) return null;
  const rows = await db
    .select()
    .from(projects)
    .where(eq(projects.id, id))
    .limit(1);
  return rows[0] ?? null;
}

export async function getProjectById(id: string) {
  if (!UUID_RE.test(id)) return null;
  const rows = await db
    .select({
      ...listColumns,
      updatedAt: projects.updatedAt,
      supervisorId: projects.supervisorId,
      ownerUniversity: profiles.university,
      ownerCareerStage: profiles.careerStage,
      ownerVerified: profiles.isVerified,
      ownerCanSupervise: profiles.canSupervise,
    })
    .from(projects)
    .leftJoin(profiles, eq(profiles.id, projects.ownerId))
    .where(eq(projects.id, id))
    .limit(1);
  return rows[0] ?? null;
}

export async function getProjectsByOwner(ownerId: string) {
  return db
    .select(listColumns)
    .from(projects)
    .leftJoin(profiles, eq(profiles.id, projects.ownerId))
    .where(eq(projects.ownerId, ownerId))
    .orderBy(desc(projects.createdAt));
}
