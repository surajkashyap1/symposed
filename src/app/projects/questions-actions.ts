"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { listingQuestions, projects } from "@/db/schema";
import { requireUser } from "@/lib/auth";
import { isUuid } from "@/lib/utils";
import { notify } from "@/lib/notify";
import { countWords } from "@/lib/profile";
import { QUESTION_WORD_LIMIT } from "@/lib/listing-meta";
import { detectSensitiveInfo, sensitiveInfoMessage } from "@/lib/sensitive-info";

const MAX_ANSWER_CHARS = 1000;

function backTo(projectId: string, error?: string): never {
  const qs = error ? `?error=${encodeURIComponent(error)}#qa` : "#qa";
  redirect(`/projects/${projectId}${qs}`);
}

// Anyone signed in can ask a public question on an open listing.
export async function askQuestion(formData: FormData) {
  const user = await requireUser();
  const projectId = String(formData.get("projectId") ?? "");
  const question = String(formData.get("question") ?? "").trim();
  if (!isUuid(projectId)) redirect("/projects");
  if (!question) backTo(projectId, "Question can't be empty.");
  if (countWords(question) > QUESTION_WORD_LIMIT)
    backTo(projectId, `Keep questions to ${QUESTION_WORD_LIMIT} words or fewer.`);
  // Q&A is public content — no contact details or patient identifiers.
  const questionFindings = detectSensitiveInfo(question);
  if (questionFindings.length > 0)
    backTo(projectId, sensitiveInfoMessage(questionFindings));

  const [project] = await db
    .select({ id: projects.id, status: projects.status, ownerId: projects.ownerId, title: projects.title })
    .from(projects)
    .where(eq(projects.id, projectId))
    .limit(1);
  if (!project) redirect("/projects");
  if (project.status !== "open")
    backTo(projectId, "This listing is no longer open.");

  await db.insert(listingQuestions).values({
    projectId,
    askerId: user.id,
    question,
  });

  await notify({
    profileId: project.ownerId,
    actorId: user.id,
    type: "system",
    title: "New question on your listing",
    body: `Someone asked about “${project.title}”.`,
    link: `/projects/${projectId}#qa`,
  });

  revalidatePath(`/projects/${projectId}`);
  backTo(projectId);
}

// Only the project owner can answer.
export async function answerQuestion(formData: FormData) {
  const user = await requireUser();
  const id = String(formData.get("id") ?? "");
  const projectId = String(formData.get("projectId") ?? "");
  const answer = String(formData.get("answer") ?? "").trim();
  if (!isUuid(id) || !isUuid(projectId)) redirect("/projects");
  if (!answer) backTo(projectId, "Answer can't be empty.");
  if (answer.length > MAX_ANSWER_CHARS)
    backTo(projectId, `Keep answers under ${MAX_ANSWER_CHARS} characters.`);
  // Q&A is public content — no contact details or patient identifiers.
  const answerFindings = detectSensitiveInfo(answer);
  if (answerFindings.length > 0)
    backTo(projectId, sensitiveInfoMessage(answerFindings));

  // Confirm ownership of the project this question belongs to.
  const [owned] = await db
    .select({ id: projects.id, title: projects.title })
    .from(projects)
    .where(and(eq(projects.id, projectId), eq(projects.ownerId, user.id)))
    .limit(1);
  if (!owned) redirect(`/projects/${projectId}`);

  const [q] = await db
    .select({ askerId: listingQuestions.askerId })
    .from(listingQuestions)
    .where(and(eq(listingQuestions.id, id), eq(listingQuestions.projectId, projectId)))
    .limit(1);

  await db
    .update(listingQuestions)
    .set({ answer, answeredAt: new Date() })
    .where(
      and(eq(listingQuestions.id, id), eq(listingQuestions.projectId, projectId))
    );

  if (q) {
    await notify({
      profileId: q.askerId,
      actorId: user.id,
      type: "system",
      title: "Your question was answered",
      body: `The lister replied about “${owned.title}”.`,
      link: `/projects/${projectId}#qa`,
    });
  }

  revalidatePath(`/projects/${projectId}`);
  backTo(projectId);
}
