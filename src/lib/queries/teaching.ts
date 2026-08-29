import { asc, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { teachingSubmissions, teachingTopics } from "@/db/schema";

export async function listTeachingTopics() {
  return db
    .select()
    .from(teachingTopics)
    .orderBy(asc(teachingTopics.sortOrder), asc(teachingTopics.id));
}

// The caller's most recent submission — drives the status strip on /teach
// and the resubmission flow when revisions are requested.
export async function getMyLatestSubmission(profileId: string) {
  const [row] = await db
    .select()
    .from(teachingSubmissions)
    .where(eq(teachingSubmissions.profileId, profileId))
    .orderBy(desc(teachingSubmissions.createdAt))
    .limit(1);
  return row ?? null;
}

export async function getSubmissionByClinicianToken(token: string) {
  const [row] = await db
    .select()
    .from(teachingSubmissions)
    .where(eq(teachingSubmissions.clinicianToken, token))
    .limit(1);
  return row ?? null;
}
