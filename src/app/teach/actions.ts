"use server";

import { randomBytes } from "node:crypto";
import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import {
  teachingSubmissionRevisions,
  teachingSubmissions,
  teachingTopics,
} from "@/db/schema";
import { requireUser, ensureProfile } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { notify } from "@/lib/notify";
import { createAdminClient } from "@/lib/supabase/admin";
import { getOptionalFile } from "@/lib/storage";
import { isUuid } from "@/lib/utils";
import {
  DESCRIPTION_MAX_CHARS,
  MATERIALS_MAX_BYTES,
  MATERIALS_MIME_TYPES,
  MAX_OBJECTIVES,
  MIN_OBJECTIVES,
  TEACHING_AUDIENCES_SET,
  type DeliveryFormat,
} from "@/lib/teach-meta";

const TEACHING_BUCKET = "teaching-materials";

function fail(message: string): never {
  redirect(`/teach/apply?error=${encodeURIComponent(message)}`);
}

function safeFilename(name: string): string {
  const cleaned = name
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return cleaned || "upload";
}

// Single proforma for commissioned topics and own ideas (spec §4.2). Also
// handles resubmission after "revisions requested", preserving the previous
// version in teaching_submission_revisions.
export async function submitTeachingProposal(formData: FormData) {
  const user = await requireUser();
  const profile = await ensureProfile(user);

  const submissionId = String(formData.get("submissionId") ?? "");
  const topicRaw = String(formData.get("topicId") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const sessionsPlan = String(formData.get("sessionsPlan") ?? "").trim();
  const startAvailability = String(formData.get("startAvailability") ?? "").trim();
  const relevantExperience = String(formData.get("relevantExperience") ?? "").trim();
  const applicantGmcNumber =
    String(formData.get("applicantGmcNumber") ?? "").trim() || null;
  const deliveryFormatRaw = String(formData.get("deliveryFormat") ?? "");

  const objectives = formData
    .getAll("objectives")
    .map((o) => String(o).trim())
    .filter(Boolean)
    .slice(0, MAX_OBJECTIVES);

  const audience = formData
    .getAll("audience")
    .map(String)
    .filter((a) => TEACHING_AUDIENCES_SET.has(a));

  const clinician = {
    clinicianName: String(formData.get("clinicianName") ?? "").trim(),
    clinicianGrade: String(formData.get("clinicianGrade") ?? "").trim(),
    clinicianSpecialty: String(formData.get("clinicianSpecialty") ?? "").trim(),
    clinicianInstitution: String(formData.get("clinicianInstitution") ?? "").trim(),
    clinicianGmcNumber: String(formData.get("clinicianGmcNumber") ?? "").trim(),
    clinicianEmail: String(formData.get("clinicianEmail") ?? "")
      .trim()
      .toLowerCase(),
  };

  // ---- validation ----------------------------------------------------
  if (!title || !description || !sessionsPlan || !startAvailability || !relevantExperience)
    fail("Please complete all required fields.");
  if (description.length > DESCRIPTION_MAX_CHARS)
    fail(`The description is capped at ${DESCRIPTION_MAX_CHARS} characters.`);
  if (objectives.length < MIN_OBJECTIVES)
    fail(`Please give at least ${MIN_OBJECTIVES} learning objectives.`);
  if (audience.length === 0) fail("Pick at least one target audience.");
  if (!["live_with_recordings", "live_only", "recorded_only"].includes(deliveryFormatRaw))
    fail("Please choose a delivery format.");
  if (Object.values(clinician).some((v) => !v))
    fail("Please complete the approving clinician section in full.");
  if (formData.get("clinicianAgreed") !== "on")
    fail("Please confirm your clinician has agreed to review your material.");
  if (formData.get("rightsDeclaration") !== "on")
    fail("Please confirm the content declaration.");

  let topicId: number | null = null;
  if (topicRaw !== "own") {
    const parsed = Number.parseInt(topicRaw, 10);
    if (Number.isNaN(parsed)) fail("Please choose what you're applying to.");
    const [topicRow] = await db
      .select()
      .from(teachingTopics)
      .where(eq(teachingTopics.id, parsed))
      .limit(1);
    if (!topicRow) fail("That topic no longer exists.");
    if (topicRow.status !== "accepting_submissions")
      fail("That topic is no longer accepting submissions.");
    topicId = parsed;
  }

  // ---- file upload (private bucket, service role only) ---------------
  const file = getOptionalFile(formData, "materials");
  let materialsPath: string | null = null;
  let materialsFilename: string | null = null;
  if (file) {
    if (file.size > MATERIALS_MAX_BYTES)
      fail("Your file is over the 50MB limit. Trim it down and try again.");
    if (!MATERIALS_MIME_TYPES.has(file.type))
      fail("Course material must be a PDF, PPTX or DOCX file.");
    const admin = createAdminClient();
    materialsFilename = file.name;
    materialsPath = `${user.id}/${crypto.randomUUID()}-${safeFilename(file.name)}`;
    const { error } = await admin.storage
      .from(TEACHING_BUCKET)
      .upload(materialsPath, file, { contentType: file.type, upsert: false });
    if (error) fail("Upload failed — please try again.");
  }

  const common = {
    topicId,
    applicantGmcNumber,
    title,
    description,
    learningObjectives: objectives,
    targetAudience: audience,
    sessionsPlan,
    deliveryFormat: deliveryFormatRaw as DeliveryFormat,
    startAvailability,
    relevantExperience,
    updatedAt: new Date(),
  };

  // ---- resubmission against the same record --------------------------
  if (submissionId) {
    if (!isUuid(submissionId)) redirect("/teach/apply");
    const [existing] = await db
      .select()
      .from(teachingSubmissions)
      .where(
        and(
          eq(teachingSubmissions.id, submissionId),
          eq(teachingSubmissions.profileId, user.id),
          eq(teachingSubmissions.status, "revisions_requested")
        )
      )
      .limit(1);
    if (!existing) redirect("/teach/apply");

    // Preserve the outgoing version before overwriting (spec §4.2).
    await db.insert(teachingSubmissionRevisions).values({
      submissionId: existing.id,
      payload: JSON.stringify({
        title: existing.title,
        description: existing.description,
        learningObjectives: existing.learningObjectives,
        targetAudience: existing.targetAudience,
        sessionsPlan: existing.sessionsPlan,
        deliveryFormat: existing.deliveryFormat,
        startAvailability: existing.startAvailability,
        relevantExperience: existing.relevantExperience,
        materialsPath: existing.materialsPath,
        materialsFilename: existing.materialsFilename,
        adminFeedback: existing.adminFeedback,
        savedAt: new Date().toISOString(),
      }),
    });

    const clinicianChanged =
      clinician.clinicianEmail !== existing.clinicianEmail;
    await db
      .update(teachingSubmissions)
      .set({
        ...common,
        ...clinician,
        ...(materialsPath && materialsFilename
          ? { materialsPath, materialsFilename }
          : {}),
        status: "submitted",
        // A different clinician must confirm afresh.
        ...(clinicianChanged
          ? {
              clinicianStatus: "pending" as const,
              clinicianRespondedAt: null,
              clinicianToken: randomBytes(24).toString("base64url"),
            }
          : {}),
      })
      .where(eq(teachingSubmissions.id, existing.id));

    const [updated] = await db
      .select()
      .from(teachingSubmissions)
      .where(eq(teachingSubmissions.id, existing.id))
      .limit(1);
    if (clinicianChanged) await emailClinician(updated);
    redirect("/teach/apply?submitted=1");
  }

  // ---- new submission ------------------------------------------------
  if (!materialsPath || !materialsFilename)
    fail("Please upload your course outline, syllabus or draft slides.");

  const token = randomBytes(24).toString("base64url");
  const [created] = await db
    .insert(teachingSubmissions)
    .values({
      profileId: user.id,
      ...common,
      ...clinician,
      materialsPath,
      materialsFilename,
      clinicianToken: token,
    })
    .returning();

  await emailClinician(created);
  await sendEmail({
    to: profile.email,
    subject: "Symposed: we've received your teaching proposal",
    text: [
      `Hi ${profile.fullName},`,
      "",
      `Thanks for proposing "${title}". It's now in our review queue and will be assessed on a rolling basis against the published rubric (${process.env.NEXT_PUBLIC_SITE_URL ?? ""}/teach).`,
      "",
      `We've emailed ${clinician.clinicianName} to confirm they've agreed to review your material — your course can't be published until they confirm, so do let them know to expect the email.`,
      "",
      "We'll be in touch with the outcome or with feedback.",
    ].join("\n"),
  });

  redirect("/teach/apply?submitted=1");
}

type SubmissionRow = typeof teachingSubmissions.$inferSelect;

// The platform contacts the clinician directly — an applicant-forwarded
// confirmation is trivially forged (spec §4.2).
async function emailClinician(s: SubmissionRow) {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  await sendEmail({
    to: s.clinicianEmail,
    subject: "Symposed: please confirm you'll review a teaching course",
    text: [
      `Dear ${s.clinicianName},`,
      "",
      `You've been named as the approving clinician for a proposed teaching course on Symposed, a platform connecting students and doctors with research and teaching opportunities:`,
      "",
      `  Course: ${s.title}`,
      `  Sessions: ${s.sessionsPlan}`,
      "",
      "The proposer has confirmed you've agreed to review the material for clinical accuracy and safety before it goes live. Please confirm or decline here:",
      "",
      `${base}/teach/verify/${s.clinicianToken}`,
      "",
      "If you haven't agreed to this, or don't recognise the proposer, choose \"Decline\" on the same page.",
    ].join("\n"),
  });
}

// ---- clinician confirm / decline (no login; the token is the identity) ---

export async function respondToClinicianRequest(formData: FormData) {
  const token = String(formData.get("token") ?? "");
  const decision = String(formData.get("decision") ?? "");
  if (!token || !["confirm", "decline"].includes(decision)) redirect("/");

  const [submission] = await db
    .select()
    .from(teachingSubmissions)
    .where(eq(teachingSubmissions.clinicianToken, token))
    .limit(1);
  if (!submission || submission.clinicianStatus !== "pending")
    redirect(`/teach/verify/${token}`);

  await db
    .update(teachingSubmissions)
    .set({
      clinicianStatus: decision === "confirm" ? "confirmed" : "declined",
      clinicianRespondedAt: new Date(),
      updatedAt: new Date(),
    })
    .where(eq(teachingSubmissions.id, submission.id));

  await notify({
    profileId: submission.profileId,
    type: "system",
    title:
      decision === "confirm"
        ? "Your approving clinician has confirmed"
        : "Your approving clinician has declined",
    body:
      decision === "confirm"
        ? `${submission.clinicianName} confirmed they'll review "${submission.title}".`
        : `${submission.clinicianName} declined the review request for "${submission.title}". You'll need to name a different approving clinician.`,
    link: "/teach",
  });

  redirect(`/teach/verify/${token}?done=1`);
}
