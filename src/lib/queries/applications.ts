import { and, count, desc, eq, gte, sql } from "drizzle-orm";
import { db } from "@/db";
import {
  applications,
  profileCertifications,
  profileSkills,
  projects,
  profiles,
  reviews,
  skills,
} from "@/db/schema";
import {
  APPLICATION_WINDOW_DAYS,
  BASE_APPLICATION_LIMIT,
  BONUS_APPLICATION_LIMIT,
  countWords,
  type ApplicationStatus,
} from "@/lib/application-meta";
import { projectTypeLabel } from "@/lib/project-meta";
import { scoreApplicant, type RankingResult } from "@/lib/ranking";

function windowStart(days: number): Date {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000);
}

export type ApplicationAllowance = {
  used: number;
  limit: number;
  remaining: number;
  bonus: boolean;
  windowDays: number;
  resetsAt: Date | null;
};

// Rolling-window allowance (ROADMAP §3). Computed in app logic, not a table —
// see the applications_applicant_time_idx index that backs this lookup.
export async function getApplicationAllowance(
  applicantId: string
): Promise<ApplicationAllowance> {
  const since = windowStart(APPLICATION_WINDOW_DAYS);

  // These two counts are independent — run them in one round trip's worth of
  // wall time instead of two sequential ones.
  const [[{ value: used }], [{ value: posted }]] = await Promise.all([
    db
      .select({ value: count() })
      .from(applications)
      .where(
        and(
          eq(applications.applicantId, applicantId),
          gte(applications.createdAt, since)
        )
      ),
    // Bonus eligibility: the user has posted at least one project (plan §8).
    db
      .select({ value: count() })
      .from(projects)
      .where(eq(projects.ownerId, applicantId)),
  ]);

  const bonus = posted > 0;
  const limit =
    BASE_APPLICATION_LIMIT + (bonus ? BONUS_APPLICATION_LIMIT : 0);

  // When the oldest application in the window ages out, one slot frees up.
  let resetsAt: Date | null = null;
  if (used >= limit) {
    const [oldest] = await db
      .select({ createdAt: applications.createdAt })
      .from(applications)
      .where(
        and(
          eq(applications.applicantId, applicantId),
          gte(applications.createdAt, since)
        )
      )
      .orderBy(applications.createdAt)
      .limit(1);
    if (oldest) {
      resetsAt = new Date(
        oldest.createdAt.getTime() + APPLICATION_WINDOW_DAYS * 24 * 60 * 60 * 1000
      );
    }
  }

  return {
    used,
    limit,
    remaining: Math.max(0, limit - used),
    bonus,
    windowDays: APPLICATION_WINDOW_DAYS,
    resetsAt,
  };
}

// Has this user already applied to this project? (unique constraint backs this)
export async function getMyApplication(projectId: string, applicantId: string) {
  const rows = await db
    .select()
    .from(applications)
    .where(
      and(
        eq(applications.projectId, projectId),
        eq(applications.applicantId, applicantId)
      )
    )
    .limit(1);
  return rows[0] ?? null;
}

export type MyApplicationItem = {
  id: string;
  status: ApplicationStatus;
  createdAt: Date;
  motivation: string;
  projectId: string;
  projectTitle: string;
  projectStatus: string;
  projectTypeLabel: string;
  projectOwnerId: string;
  // Lister's contact details — populated only once this application is
  // accepted (auto-reveal). null otherwise so unrevealed contacts never reach
  // the client.
  listerName: string | null;
  listerEmail: string | null;
  listerPhone: string | null;
};

// Applicant dashboard: the current user's applications with project context.
export async function getApplicationsByApplicant(
  applicantId: string
): Promise<MyApplicationItem[]> {
  const rows = await db
    .select({
      id: applications.id,
      status: applications.status,
      createdAt: applications.createdAt,
      motivation: applications.motivation,
      projectId: projects.id,
      projectTitle: projects.title,
      projectStatus: projects.status,
      projectType: projects.projectType,
      projectOwnerId: projects.ownerId,
      listerName: profiles.fullName,
      listerEmail: profiles.email,
      listerPhone: profiles.contactPhone,
    })
    .from(applications)
    .innerJoin(projects, eq(projects.id, applications.projectId))
    .innerJoin(profiles, eq(profiles.id, projects.ownerId))
    .where(eq(applications.applicantId, applicantId))
    .orderBy(desc(applications.createdAt));

  return rows.map((r) => {
    const revealed = r.status === "accepted";
    return {
      id: r.id,
      status: r.status,
      createdAt: r.createdAt,
      motivation: r.motivation,
      projectId: r.projectId,
      projectTitle: r.projectTitle,
      projectStatus: r.projectStatus,
      projectTypeLabel: projectTypeLabel(r.projectType),
      projectOwnerId: r.projectOwnerId,
      listerName: revealed ? r.listerName : null,
      listerEmail: revealed ? r.listerEmail : null,
      listerPhone: revealed ? r.listerPhone : null,
    };
  });
}

export type ApplicantItem = {
  id: string;
  status: ApplicationStatus;
  createdAt: Date;
  motivation: string;
  suitability: string;
  hoursPerWeek: number | null;
  skillsSummary: string | null;
  applicantId: string;
  applicantName: string | null;
  applicantUniversity: string | null;
  applicantCareerStage: string;
  applicantVerified: boolean;
  applicantNewResearcher: boolean;
  applicantAvailabilityHoursPerWeek: number | null;
  applicantPreferredProjectTypes: string | null;
  applicantPreferredSpecialties: string | null;
  applicantSkills: string | null;
  applicantCertificationCount: number;
  // Applicant's contact details — populated only once accepted (auto-reveal).
  applicantEmail: string | null;
  applicantPhone: string | null;
};

export type ProjectRankMeta = {
  isBeginnerFriendly: boolean;
  specialty: string | null;
  roleCategory: string | null;
};

export type RankedApplicant = ApplicantItem & { ranking: RankingResult };

// Lister view with fair ranking (ROADMAP §6). Pulls the extra applicant signals
// the scorer needs, computes a transparent score, and orders undecided
// applicants by it (shortlisted first, decided/withdrawn last).
export async function getRankedApplicantsForProject(
  projectId: string,
  project: ProjectRankMeta
): Promise<RankedApplicant[]> {
  const reviewCount = sql<number>`(
    select count(*)::int from ${reviews} rv
    where rv.reviewee_id = ${profiles.id}
      and rv.direction = 'supervisor_to_member'
  )`;
  const applicantSkills = sql<string | null>`(
    select string_agg(sk.name, ', ' order by sk.name)
    from ${profileSkills} ps
    inner join ${skills} sk on sk.id = ps.skill_id
    where ps.profile_id = ${profiles.id}
  )`;
  const applicantCertificationCount = sql<number>`(
    select count(*)::int from ${profileCertifications} pc
    where pc.profile_id = ${profiles.id}
  )`;

  const rows = await db
    .select({
      id: applications.id,
      status: applications.status,
      createdAt: applications.createdAt,
      motivation: applications.motivation,
      suitability: applications.suitability,
      hoursPerWeek: applications.hoursPerWeek,
      skillsSummary: applications.skillsSummary,
      applicantId: profiles.id,
      applicantName: profiles.fullName,
      applicantUniversity: profiles.university,
      applicantCareerStage: profiles.careerStage,
      applicantVerified: profiles.isVerified,
      applicantNewResearcher: profiles.isNewResearcher,
      applicantAvailabilityHoursPerWeek: profiles.availabilityHoursPerWeek,
      applicantPreferredProjectTypes: profiles.preferredProjectTypes,
      applicantPreferredSpecialties: profiles.preferredSpecialties,
      applicantSkills,
      applicantCertificationCount,
      applicantEmail: profiles.email,
      applicantPhone: profiles.contactPhone,
      reliabilityScore: profiles.reliabilityScore,
      profileCompleteness: profiles.profileCompleteness,
      applicantSpecialty: profiles.specialty,
      reviewCount,
    })
    .from(applications)
    .innerJoin(profiles, eq(profiles.id, applications.applicantId))
    .where(eq(applications.projectId, projectId))
    .orderBy(desc(applications.createdAt));

  const statusRank: Record<ApplicationStatus, number> = {
    shortlisted: 0,
    pending: 1,
    accepted: 2,
    rejected: 3,
    withdrawn: 4,
  };

  return rows
    .map((r) => {
      const ranking = scoreApplicant({
        reliabilityScore: r.reliabilityScore != null ? Number(r.reliabilityScore) : null,
        reviewCount: r.reviewCount,
        isNewResearcher: r.applicantNewResearcher,
        profileCompleteness: r.profileCompleteness,
        hasAvailability:
          r.applicantAvailabilityHoursPerWeek != null &&
          r.applicantAvailabilityHoursPerWeek > 0,
        applicantSpecialty: r.applicantSpecialty,
        skillsSummary: [r.skillsSummary, r.applicantSkills].filter(Boolean).join(", "),
        motivationWords: countWords(`${r.motivation} ${r.suitability}`),
        beginnerFriendly: project.isBeginnerFriendly,
        projectSpecialty: project.specialty,
        roleCategory: project.roleCategory,
      });
      return {
        id: r.id,
        status: r.status,
        createdAt: r.createdAt,
        motivation: r.motivation,
        suitability: r.suitability,
        hoursPerWeek: r.hoursPerWeek,
        skillsSummary: r.skillsSummary,
        applicantId: r.applicantId,
        applicantName: r.applicantName,
        applicantUniversity: r.applicantUniversity,
        applicantCareerStage: r.applicantCareerStage,
        applicantVerified: r.applicantVerified,
        applicantNewResearcher: r.applicantNewResearcher,
        applicantAvailabilityHoursPerWeek: r.applicantAvailabilityHoursPerWeek,
        applicantPreferredProjectTypes: r.applicantPreferredProjectTypes,
        applicantPreferredSpecialties: r.applicantPreferredSpecialties,
        applicantSkills: r.applicantSkills,
        applicantCertificationCount: r.applicantCertificationCount,
        applicantEmail: r.status === "accepted" ? r.applicantEmail : null,
        applicantPhone: r.status === "accepted" ? r.applicantPhone : null,
        ranking,
      };
    })
    .sort(
      (a, b) =>
        statusRank[a.status] - statusRank[b.status] ||
        b.ranking.score - a.ranking.score
    );
}
