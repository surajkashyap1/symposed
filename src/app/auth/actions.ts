"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { eq, inArray } from "drizzle-orm";
import { db } from "@/db";
import { profileCertifications, profiles, profileSkills, skills } from "@/db/schema";
import { createClient } from "@/lib/supabase/server";
import { ensureProfile, requireUser } from "@/lib/auth";
import {
  computeCompleteness,
  countWords,
  CAREER_STAGES,
  parseHoursPerWeek,
  parseListText,
  parseSkillNames,
  SPECIALTY_WORD_LIMIT,
  SUMMARY_WORD_LIMIT,
  type Profile,
} from "@/lib/profile";
import { getOptionalFile, uploadProfileAsset } from "@/lib/storage";

export async function login(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const next = String(formData.get("next") ?? "/dashboard");

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    redirect(`/login?error=${encodeURIComponent(error.message)}`);
  }
  revalidatePath("/", "layout");
  // Internal paths only: "//evil.com" is a protocol-relative external URL.
  redirect(next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
}

export async function signup(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const fullName = String(formData.get("fullName") ?? "").trim();

  const existingProfile = await db
    .select({ id: profiles.id })
    .from(profiles)
    .where(eq(profiles.email, email))
    .limit(1);
  if (existingProfile.length > 0) {
    redirect(
      `/signup?error=${encodeURIComponent(
        "An account already exists for this email. Log in instead."
      )}`
    );
  }

  const supabase = await createClient();
  const origin = (await headers()).get("origin") ?? "";
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { full_name: fullName },
      emailRedirectTo: `${origin}/auth/confirm?next=/onboarding`,
    },
  });

  if (error) {
    redirect(`/signup?error=${encodeURIComponent(error.message)}`);
  }

  const identities = data.user?.identities;
  if (identities && identities.length === 0) {
    redirect(
      `/signup?error=${encodeURIComponent(
        "An account already exists for this email. Log in instead."
      )}`
    );
  }

  // If email confirmation is disabled, we get a session immediately.
  if (data.session && data.user) {
    await ensureProfile(data.user);
    revalidatePath("/", "layout");
    redirect("/onboarding");
  }

  // Otherwise the user must click the link in their email.
  redirect("/signup?check=email");
}

export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  revalidatePath("/", "layout");
  redirect("/");
}

const VALID_STAGES = new Set(CAREER_STAGES.map((s) => s.value));

export async function updateProfile(formData: FormData) {
  const user = await requireUser();

  // Enforce the word limits the form shows, before any file upload work.
  const specialtyRaw = String(formData.get("specialty") ?? "").trim();
  const summaryRaw = String(formData.get("summary") ?? "").trim();
  if (countWords(specialtyRaw) > SPECIALTY_WORD_LIMIT)
    redirect(
      `/onboarding?error=${encodeURIComponent(
        `Specialty must be ${SPECIALTY_WORD_LIMIT} words or fewer.`
      )}`
    );
  if (countWords(summaryRaw) > SUMMARY_WORD_LIMIT)
    redirect(
      `/onboarding?error=${encodeURIComponent(
        `About you must be ${SUMMARY_WORD_LIMIT} words or fewer.`
      )}`
    );

  const stageRaw = String(formData.get("careerStage") ?? "other");
  const careerStage = (
    VALID_STAGES.has(stageRaw as Profile["careerStage"]) ? stageRaw : "other"
  ) as Profile["careerStage"];
  const careerStageOther =
    careerStage === "other"
      ? String(formData.get("careerStageOther") ?? "").trim() || null
      : null;

  let linkedinUrl = String(formData.get("linkedinUrl") ?? "").trim() || null;
  if (linkedinUrl && !/^https?:\/\//i.test(linkedinUrl)) {
    linkedinUrl = `https://${linkedinUrl}`;
  }

  const avatarFile = getOptionalFile(formData, "avatar");
  let avatarUrl = String(formData.get("existingAvatarUrl") ?? "").trim() || null;
  if (avatarFile) {
    try {
      avatarUrl = await uploadProfileAsset({
        userId: user.id,
        file: avatarFile,
        folder: "avatars",
      });
    } catch (error) {
      redirect(
        `/onboarding?error=${encodeURIComponent(
          error instanceof Error ? error.message : "Could not upload profile picture."
        )}`
      );
    }
  }

  const fields = {
    fullName: String(formData.get("fullName") ?? "").trim(),
    university: String(formData.get("university") ?? "").trim() || null,
    specialty: specialtyRaw || null,
    summary: summaryRaw || null,
    availability: null,
    availabilityHoursPerWeek: parseHoursPerWeek(
      formData.get("availabilityHoursPerWeek")
    ),
    avatarUrl,
    preferredProjectTypes: parseListText(formData.get("preferredProjectTypes")),
    preferredSpecialties: parseListText(formData.get("preferredSpecialties")),
    careerStage,
    careerStageOther,
    linkedinUrl,
  };

  const completeness = computeCompleteness(fields as Partial<Profile>);

  const skillNames = parseSkillNames(formData.get("skills"));
  const certNames = formData
    .getAll("certName")
    .map((value) => String(value ?? "").trim());
  const existingProofUrls = formData
    .getAll("certProofUrl")
    .map((value) => String(value ?? "").trim());
  const proofFiles = formData.getAll("certProofFile");

  const certifications: { name: string; proofUrl: string | null }[] = [];
  for (let i = 0; i < certNames.length; i++) {
    const name = certNames[i];
    if (!name) continue;

    let proofUrl = existingProofUrls[i] || null;
    const proofFile = proofFiles[i];
    if (proofFile instanceof File && proofFile.size > 0) {
      try {
        proofUrl = await uploadProfileAsset({
          userId: user.id,
          file: proofFile,
          folder: "certifications",
        });
      } catch (error) {
        redirect(
          `/onboarding?error=${encodeURIComponent(
            error instanceof Error
              ? error.message
              : "Could not upload certificate proof."
          )}`
        );
      }
    }

    certifications.push({ name, proofUrl });
  }

  await db.transaction(async (tx) => {
    await tx
      .update(profiles)
      .set({ ...fields, profileCompleteness: completeness, updatedAt: new Date() })
      .where(eq(profiles.id, user.id));

    await tx.delete(profileSkills).where(eq(profileSkills.profileId, user.id));
    if (skillNames.length > 0) {
      await tx
        .insert(skills)
        .values(skillNames.map((name) => ({ name })))
        .onConflictDoNothing();

      const skillRows = await tx
        .select({ id: skills.id })
        .from(skills)
        .where(inArray(skills.name, skillNames));

      if (skillRows.length > 0) {
        await tx.insert(profileSkills).values(
          skillRows.map((skill) => ({
            profileId: user.id,
            skillId: skill.id,
          }))
        );
      }
    }

    await tx
      .delete(profileCertifications)
      .where(eq(profileCertifications.profileId, user.id));
    if (certifications.length > 0) {
      await tx.insert(profileCertifications).values(
        certifications.map((certification) => ({
          profileId: user.id,
          name: certification.name,
          proofUrl: certification.proofUrl,
        }))
      );
    }
  });

  revalidatePath("/dashboard");
  revalidatePath(`/profile/${user.id}`);
  redirect("/dashboard");
}
