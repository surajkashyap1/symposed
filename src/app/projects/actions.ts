"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { projects } from "@/db/schema";
import { requireUser, requirePoster } from "@/lib/auth";
import { isUuid } from "@/lib/utils";
import { detectSensitiveInfo, sensitiveInfoMessage } from "@/lib/sensitive-info";
import { awardBadge } from "@/lib/badges";
import {
  PROJECT_TYPE_VALUES,
  EXPERIENCE_VALUES,
  type ProjectType,
  type ExperienceLevel,
} from "@/lib/project-meta";

function parseProjectForm(formData: FormData) {
  const typeRaw = String(formData.get("projectType") ?? "other");
  const expRaw = String(formData.get("experienceLevel") ?? "beginner_welcome");

  const projectType = (
    PROJECT_TYPE_VALUES.has(typeRaw as ProjectType) ? typeRaw : "other"
  ) as ProjectType;
  const experienceLevel = (
    EXPERIENCE_VALUES.has(expRaw as ExperienceLevel) ? expRaw : "beginner_welcome"
  ) as ExperienceLevel;

  // Only accept a real yyyy-mm-dd value — anything else would fail the
  // Postgres date cast with a 500 instead of a form error.
  const deadlineRaw = String(formData.get("applicationDeadline") ?? "").trim();
  const deadline = /^\d{4}-\d{2}-\d{2}$/.test(deadlineRaw) ? deadlineRaw : null;
  const positions = parseInt(
    String(formData.get("positionsAvailable") ?? "1"),
    10
  );

  return {
    title: String(formData.get("title") ?? "").trim(),
    description: String(formData.get("description") ?? "").trim(),
    projectType,
    experienceLevel,
    specialty: String(formData.get("specialty") ?? "").trim() || null,
    roleCategory: String(formData.get("roleCategory") ?? "").trim() || null,
    isBeginnerFriendly:
      formData.get("isBeginnerFriendly") === "on" ||
      experienceLevel === "beginner_welcome",
    positionsAvailable: Number.isFinite(positions)
      ? Math.min(Math.max(positions, 1), 50)
      : 1,
    applicationDeadline: deadline,
  };
}

// Listings are public: block contact details and patient identifiers
// (Acceptable Use Policy §3, Contact Sharing Policy §1). The confirmation
// checkbox is also enforced here, not just in the form markup.
function checkListingSubmission(
  formData: FormData,
  data: ReturnType<typeof parseProjectForm>,
  backTo: string
) {
  if (formData.get("noConfidentialInfo") !== "on") {
    redirect(
      `${backTo}?error=${encodeURIComponent(
        "Please confirm your listing contains no confidential or patient information."
      )}`
    );
  }
  const publicText = [data.title, data.description, data.specialty, data.roleCategory]
    .filter(Boolean)
    .join("\n");
  const findings = detectSensitiveInfo(publicText);
  if (findings.length > 0) {
    redirect(`${backTo}?error=${encodeURIComponent(sensitiveInfoMessage(findings))}`);
  }
}

export async function createProject(formData: FormData) {
  const { user } = await requirePoster();
  const data = parseProjectForm(formData);
  const isSupervisor = formData.get("isSupervisor") === "on";

  if (!data.title || !data.description) {
    redirect("/projects/new?error=Title+and+description+are+required");
  }
  checkListingSubmission(formData, data, "/projects/new");

  const [created] = await db
    .insert(projects)
    .values({
      ownerId: user.id,
      status: "open",
      supervisorId: isSupervisor ? user.id : null,
      ...data,
    })
    .returning({ id: projects.id });

  revalidatePath("/projects");
  // ?published=1 drives the "browse people currently available" cross-link —
  // the moment a lister most needs the reverse board.
  redirect(`/projects/${created.id}?published=1`);
}

export async function updateProject(formData: FormData) {
  const { user } = await requirePoster();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/projects");
  const data = parseProjectForm(formData);
  const isSupervisor = formData.get("isSupervisor") === "on";

  if (!id || !data.title || !data.description) {
    redirect(`/projects/${id}/edit?error=Title+and+description+are+required`);
  }
  checkListingSubmission(formData, data, `/projects/${id}/edit`);

  // Owner guard: the where clause only matches if this user owns the project.
  await db
    .update(projects)
    .set({
      ...data,
      supervisorId: isSupervisor ? user.id : null,
      updatedAt: new Date(),
    })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id)));

  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
  redirect(`/projects/${id}`);
}

export async function closeProject(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/projects");

  await db
    .update(projects)
    .set({ status: "closed", updatedAt: new Date() })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id)));

  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
  redirect(`/projects/${id}`);
}

export async function completeProject(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/projects");

  // Owner guard via where clause; only award if a row was actually updated.
  const updated = await db
    .update(projects)
    .set({ status: "completed", updatedAt: new Date() })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id)))
    .returning({ id: projects.id });
  if (!updated.length) redirect(`/projects/${id}`);

  // Leading a project to completion earns the Project Lead badge (ROADMAP §5).
  await awardBadge(user.id, "project_lead");

  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
  redirect(`/projects/${id}`);
}

export async function reopenProject(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  if (!isUuid(id)) redirect("/projects");

  await db
    .update(projects)
    .set({ status: "open", updatedAt: new Date() })
    .where(and(eq(projects.id, id), eq(projects.ownerId, user.id)));

  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
  redirect(`/projects/${id}`);
}
