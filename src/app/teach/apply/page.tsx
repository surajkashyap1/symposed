import Link from "next/link";
import { requireUser, ensureProfile } from "@/lib/auth";
import { listTeachingTopics, getMyLatestSubmission } from "@/lib/queries/teaching";
import { CAREER_STAGES } from "@/lib/profile";
import {
  DESCRIPTION_MAX_CHARS,
  MATERIALS_ACCEPT,
  MAX_OBJECTIVES,
  TEACHING_AUDIENCES,
} from "@/lib/teach-meta";
import { submitTeachingProposal } from "@/app/teach/actions";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { TeachFormatField } from "@/components/teach-format-field";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Propose a course — Symposed" };

export default async function TeachApplyPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; submitted?: string; topic?: string }>;
}) {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const [{ error, submitted, topic }, topics, mine] = await Promise.all([
    searchParams,
    listTeachingTopics(),
    getMyLatestSubmission(user.id),
  ]);

  // Resubmission: revisions_requested reopens the same record.
  const revising = mine?.status === "revisions_requested" ? mine : null;

  if (submitted) {
    return (
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
        <Card>
          <CardHeader>
            <CardTitle>Submission received</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-4 text-sm leading-relaxed text-muted-foreground">
            <p>
              Thanks — your proposal is in the review queue. We&apos;ve emailed
              your approving clinician directly to confirm they&apos;ve agreed
              to review your material; your course can&apos;t go live until
              they confirm, so it&apos;s worth letting them know to expect the
              email.
            </p>
            <p>
              We review on a rolling basis against the published rubric. If
              revisions are needed you&apos;ll get specific written feedback
              and can resubmit.
            </p>
            <Link href="/teach" className={buttonVariants({ variant: "outline" })}>
              Back to teaching
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  const defaultTopic = revising
    ? (revising.topicId ?? "own")
    : topics.some((t) => String(t.id) === topic && t.status === "accepting_submissions")
      ? topic!
      : "";

  const objectiveDefaults = revising?.learningObjectives ?? [];

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>
            {revising ? "Revise your proposal" : "Propose a course"}
          </CardTitle>
          <CardDescription>
            {revising ? (
              <>
                Your reviewer asked for changes. Edit below and resubmit — the
                previous version is kept in the record&apos;s history.
              </>
            ) : (
              <>
                One form for both commissioned topics and your own ideas.
                Submissions are reviewed on a rolling basis against the{" "}
                <Link href="/teach#topics" className="text-primary underline">
                  published rubric
                </Link>
                .
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {revising?.adminFeedback && (
            <div className="mb-5 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
              <p className="font-semibold">Reviewer feedback</p>
              <p className="mt-1 whitespace-pre-wrap">{revising.adminFeedback}</p>
            </div>
          )}
          <form action={submitTeachingProposal} className="flex flex-col gap-5">
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}
            {revising && (
              <input type="hidden" name="submissionId" value={revising.id} />
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="fullName">Full name</Label>
                <Input
                  id="fullName"
                  name="fullName"
                  required
                  defaultValue={profile.fullName}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  required
                  defaultValue={profile.email}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="grade">Current grade or role</Label>
                <Select
                  id="grade"
                  name="grade"
                  required
                  defaultValue={profile.careerStage ?? ""}
                  options={CAREER_STAGES.map((s) => ({
                    value: s.value,
                    label: s.label,
                  }))}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="institution">Institution</Label>
                <Input
                  id="institution"
                  name="institution"
                  required
                  defaultValue={profile.university ?? ""}
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="applicantGmcNumber">
                GMC or GDC number (required only for qualified clinicians)
              </Label>
              <Input
                id="applicantGmcNumber"
                name="applicantGmcNumber"
                defaultValue={revising?.applicantGmcNumber ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="topicId">I am applying to</Label>
              <Select
                id="topicId"
                name="topicId"
                required
                defaultValue={String(defaultTopic)}
                placeholder="Choose a topic or propose your own"
                options={[
                  ...topics.map((t) => ({
                    value: String(t.id),
                    label: t.title,
                    disabled: t.status !== "accepting_submissions",
                  })),
                  { value: "own", label: "Proposing my own topic" },
                ]}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="title">Proposed course title</Label>
              <Input
                id="title"
                name="title"
                required
                defaultValue={revising?.title ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="description">Course description</Label>
              <Textarea
                id="description"
                name="description"
                required
                rows={5}
                maxLength={DESCRIPTION_MAX_CHARS}
                placeholder="What the course covers, how sessions build on each other, and what a learner leaves able to do."
                defaultValue={revising?.description ?? ""}
              />
              <p className="text-xs text-muted-foreground">
                Up to {DESCRIPTION_MAX_CHARS} characters.
              </p>
            </div>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">
                Learning objectives (3 to 5)
              </legend>
              {Array.from({ length: MAX_OBJECTIVES }, (_, i) => (
                <Input
                  key={i}
                  name="objectives"
                  required={i < 3}
                  placeholder={`Objective ${i + 1}${i >= 3 ? " (optional)" : ""}`}
                  defaultValue={objectiveDefaults[i] ?? ""}
                />
              ))}
            </fieldset>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Target audience</legend>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                {TEACHING_AUDIENCES.map((a) => (
                  <label key={a} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      name="audience"
                      value={a}
                      defaultChecked={revising?.targetAudience.includes(a) ?? false}
                      className="h-4 w-4 rounded border-input accent-primary"
                    />
                    {a}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="sessionsPlan">Sessions and duration</Label>
                <Input
                  id="sessionsPlan"
                  name="sessionsPlan"
                  required
                  placeholder="e.g. 8 sessions of 45 minutes"
                  defaultValue={revising?.sessionsPlan ?? ""}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="startAvailability">
                  Proposed start date and availability
                </Label>
                <Input
                  id="startAvailability"
                  name="startAvailability"
                  required
                  placeholder="e.g. from October, Tuesday evenings"
                  defaultValue={revising?.startAvailability ?? ""}
                />
              </div>
            </div>

            <TeachFormatField
              defaultValue={revising?.deliveryFormat ?? "live_with_recordings"}
            />

            <div className="grid gap-2">
              <Label htmlFor="relevantExperience">Relevant experience</Label>
              <Textarea
                id="relevantExperience"
                name="relevantExperience"
                required
                rows={3}
                placeholder="Prior teaching, qualifications, and clinical experience in this area."
                defaultValue={revising?.relevantExperience ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="materials">
                Course outline, syllabus or draft slides
              </Label>
              <Input
                id="materials"
                name="materials"
                type="file"
                accept={MATERIALS_ACCEPT}
                required={!revising}
              />
              <p className="text-xs text-muted-foreground">
                PDF, PPTX or DOCX, up to 50MB.
                {revising && " Leave empty to keep your previous upload."}
              </p>
            </div>

            {/* Approving clinician */}
            <fieldset className="grid gap-4 rounded-md border bg-muted/20 p-4">
              <div>
                <legend className="text-sm font-semibold">
                  Approving clinician
                </legend>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Every course is checked for clinical accuracy and safety by a
                  GMC-registered specialist before it goes live. We&apos;ll
                  email them directly for confirmation — please let them know
                  to expect it.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="clinicianName">Name</Label>
                  <Input
                    id="clinicianName"
                    name="clinicianName"
                    required
                    defaultValue={revising?.clinicianName ?? ""}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="clinicianGrade">Grade</Label>
                  <Input
                    id="clinicianGrade"
                    name="clinicianGrade"
                    required
                    placeholder="e.g. Consultant"
                    defaultValue={revising?.clinicianGrade ?? ""}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="clinicianSpecialty">Specialty</Label>
                  <Input
                    id="clinicianSpecialty"
                    name="clinicianSpecialty"
                    required
                    defaultValue={revising?.clinicianSpecialty ?? ""}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="clinicianInstitution">Institution</Label>
                  <Input
                    id="clinicianInstitution"
                    name="clinicianInstitution"
                    required
                    defaultValue={revising?.clinicianInstitution ?? ""}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="clinicianGmcNumber">GMC number</Label>
                  <Input
                    id="clinicianGmcNumber"
                    name="clinicianGmcNumber"
                    required
                    defaultValue={revising?.clinicianGmcNumber ?? ""}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="clinicianEmail">Email</Label>
                  <Input
                    id="clinicianEmail"
                    name="clinicianEmail"
                    type="email"
                    required
                    defaultValue={revising?.clinicianEmail ?? ""}
                  />
                </div>
              </div>
              <label className="flex items-start gap-2 text-sm leading-relaxed">
                <input
                  type="checkbox"
                  name="clinicianAgreed"
                  required
                  className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
                />
                I confirm this clinician has agreed to review my material for
                clinical accuracy and safety.
              </label>
            </fieldset>

            <label className="flex items-start gap-2 text-sm leading-relaxed">
              <input
                type="checkbox"
                name="rightsDeclaration"
                required
                className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
              />
              I confirm that I own or have the right to use everything in my
              uploaded material, that it contains no patient-identifiable
              information, and that no copyrighted images are used without
              permission.
            </label>

            <Button type="submit" className="mt-2 self-start">
              {revising ? "Resubmit proposal" : "Submit proposal"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
