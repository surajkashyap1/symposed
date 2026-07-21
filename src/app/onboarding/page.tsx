import { requireUser, ensureProfile } from "@/lib/auth";
import { updateProfile } from "@/app/auth/actions";
import { requestVerification } from "@/app/onboarding/verify-actions";
import { SPECIALTY_WORD_LIMIT, SUMMARY_WORD_LIMIT } from "@/lib/profile";
import { UK_UNIVERSITIES } from "@/lib/universities";
import { getProfileEditorData } from "@/lib/queries/profiles";
import { Button } from "@/components/ui/button";
import { CareerStageField } from "@/components/career-stage-field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { WordLimitedField } from "@/components/word-limited-field";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{
    error?: string;
    verify?: string;
    link?: string;
  }>;
}) {
  const user = await requireUser();
  await ensureProfile(user);
  const [{ error, verify, link }, editorData] = await Promise.all([
    searchParams,
    getProfileEditorData(user.id),
  ]);
  const profile = editorData.profile;
  if (!profile) throw new Error("Profile could not be loaded.");
  const certificationRows = [
    ...editorData.certifications,
    ...Array.from({ length: Math.max(1, 3 - editorData.certifications.length) }, (_, i) => ({
      id: `new-${i}`,
      name: "",
      proofUrl: null,
    })),
  ];

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Your profile</CardTitle>
          <CardDescription>
            Tell supervisors who you are. You can edit this any time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={updateProfile} className="flex flex-col gap-5">
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="avatar">Profile picture (optional)</Label>
              <input
                type="hidden"
                name="existingAvatarUrl"
                value={profile.avatarUrl ?? ""}
              />
              <div className="flex items-center gap-4">
                {profile.avatarUrl ? (
                  <img
                    src={profile.avatarUrl}
                    alt=""
                    className="h-16 w-16 rounded-full border object-cover"
                  />
                ) : (
                  <div className="flex h-16 w-16 items-center justify-center rounded-full border bg-muted text-lg font-semibold text-muted-foreground">
                    {profile.fullName?.slice(0, 1).toUpperCase() ?? "U"}
                  </div>
                )}
                <Input
                  id="avatar"
                  name="avatar"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="fullName">Full name</Label>
              <Input
                id="fullName"
                name="fullName"
                required
                defaultValue={profile.fullName ?? ""}
              />
            </div>

            <CareerStageField
              defaultValue={profile.careerStage}
              defaultOther={profile.careerStageOther ?? ""}
            />

            <div className="grid gap-2">
              <Label htmlFor="university">University / institution</Label>
              <Input
                id="university"
                name="university"
                list="uk-universities"
                placeholder="Start typing to search, or enter your own"
                defaultValue={profile.university ?? ""}
              />
              <datalist id="uk-universities">
                {UK_UNIVERSITIES.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </div>

            <WordLimitedField
              id="specialty"
              name="specialty"
              label="Specialty / area of interest"
              max={SPECIALTY_WORD_LIMIT}
              placeholder="e.g. Cardiology, Public health"
              defaultValue={profile.specialty ?? ""}
            />

            <WordLimitedField
              id="summary"
              name="summary"
              label="About you"
              max={SUMMARY_WORD_LIMIT}
              multiline
              rows={4}
              placeholder="A short summary of your interests, skills, and what you're looking for."
              defaultValue={profile.summary ?? ""}
            />

            <div className="grid gap-2">
              <Label htmlFor="contactPhone">Phone number (optional)</Label>
              <Input
                id="contactPhone"
                name="contactPhone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="e.g. 07123 456789"
                defaultValue={profile.contactPhone ?? ""}
              />
              <p className="text-xs text-muted-foreground">
                Private. Never shown on your profile — only shared with the other
                person once an application is accepted. Your account email is
                always used as your contact; a phone number is optional.
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="linkedinUrl">LinkedIn profile (optional)</Label>
              <Input
                id="linkedinUrl"
                name="linkedinUrl"
                type="url"
                inputMode="url"
                placeholder="https://www.linkedin.com/in/your-handle"
                defaultValue={profile.linkedinUrl ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="availabilityHoursPerWeek">Availability (hours per week)</Label>
              <Input
                id="availabilityHoursPerWeek"
                name="availabilityHoursPerWeek"
                type="number"
                min="0"
                max="80"
                step="1"
                placeholder="e.g. 5"
                defaultValue={profile.availabilityHoursPerWeek ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="skills">Skills</Label>
              <Textarea
                id="skills"
                name="skills"
                rows={3}
                placeholder="e.g. literature screening, data extraction, statistics"
                defaultValue={editorData.skillNames.join(", ")}
              />
            </div>

            <div className="grid gap-3">
              <div>
                <Label>Certifications and proof</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add courses, certificates, or training and upload proof where useful.
                </p>
              </div>
              {certificationRows.map((certification, index) => (
                <div
                  key={certification.id}
                  className="grid gap-2 rounded-md border bg-muted/20 p-3 sm:grid-cols-[1fr_1fr]"
                >
                  <div className="grid gap-2">
                    <Label htmlFor={`certName-${index}`}>Certification</Label>
                    <Input
                      id={`certName-${index}`}
                      name="certName"
                      placeholder="e.g. GCP training"
                      defaultValue={certification.name}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor={`certProofFile-${index}`}>Proof upload</Label>
                    <input
                      type="hidden"
                      name="certProofUrl"
                      value={certification.proofUrl ?? ""}
                    />
                    <Input
                      id={`certProofFile-${index}`}
                      name="certProofFile"
                      type="file"
                      accept="application/pdf,image/png,image/jpeg,image/webp"
                    />
                    {certification.proofUrl && (
                      <a
                        href={certification.proofUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-primary hover:underline"
                      >
                        Current proof
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="preferredProjectTypes">Project types you are looking for</Label>
              <Textarea
                id="preferredProjectTypes"
                name="preferredProjectTypes"
                rows={2}
                placeholder="e.g. audit, retrospective study, poster"
                defaultValue={profile.preferredProjectTypes ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="preferredSpecialties">Specialties you are looking for</Label>
              <Textarea
                id="preferredSpecialties"
                name="preferredSpecialties"
                rows={2}
                placeholder="e.g. cardiology, surgery, public health"
                defaultValue={profile.preferredSpecialties ?? ""}
              />
            </div>

            <Button type="submit" className="mt-2 self-start">
              Save profile
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card id="verify" className="mt-6 scroll-mt-20">
        <CardHeader>
          <CardTitle>Get verified</CardTitle>
          <CardDescription>
            Verify with a <strong>.ac.uk</strong> or <strong>.nhs.uk</strong>{" "}
            email to unlock posting projects. You can verify a different address
            from the one you signed up with.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {profile.isVerified ? (
            <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm text-success-foreground">
              Your account is verified. You can post projects.
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {verify === "sent" && (
                <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
                  Check your inbox for a verification link.
                </p>
              )}
              {verify === "invalid" && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  That verification link is invalid or has expired. Request a new
                  one below.
                </p>
              )}
              {verify === "manual" && link && (
                <div className="rounded-md border border-dashed px-4 py-3 text-sm">
                  <p className="text-muted-foreground">
                    Email isn&apos;t configured yet, so use this verification
                    link directly:
                  </p>
                  <a
                    href={link}
                    className="mt-1 block break-all text-primary underline"
                  >
                    {link}
                  </a>
                </div>
              )}
              {verify && verify !== "sent" && verify !== "invalid" && verify !== "manual" && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {verify}
                </p>
              )}

              <form action={requestVerification} className="flex flex-col gap-2">
                <Label htmlFor="verifyEmail">Academic or NHS email</Label>
                <Input
                  id="verifyEmail"
                  name="verifyEmail"
                  type="email"
                  required
                  placeholder="you@example.ac.uk"
                />
                <Button type="submit" variant="outline" className="self-start">
                  Send verification link
                </Button>
              </form>

              <p className="text-xs text-muted-foreground">
                Have a different staff email?{" "}
                <a
                  href="/contact"
                  className="text-primary underline"
                >
                  Contact us
                </a>{" "}
                and we&apos;ll verify you manually.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
