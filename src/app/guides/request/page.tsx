import { requireUser, ensureProfile } from "@/lib/auth";
import {
  COLLABORATOR_HELP,
  COLLABORATOR_OPTIONS,
  DATABASE_OPTIONS,
  DELIVERY_PROMISE,
  GUIDE_GRADES,
  HOURS_OPTIONS,
  MAX_GUIDE_SPECIALTIES,
  PUBLICATION_TYPES,
  STATS_OPTIONS,
  SUPERVISOR_OPTIONS,
  TIMELINE_OPTIONS,
  TOPIC_MAX_CHARS,
  YES_NO_OPTIONS,
} from "@/lib/guides-meta";
import { submitGuideProforma } from "@/app/guides/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Start your guide | Symposed" };

const toOptions = (values: readonly string[]) =>
  values.map((v) => ({ value: v, label: v }));

export default async function GuideRequestPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const { error } = await searchParams;

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>Tell us about your interests</CardTitle>
          <CardDescription>
            About five minutes. We use this to find a question that is
            genuinely open, genuinely doable, and genuinely yours. You&apos;ll
            review everything before any payment. {DELIVERY_PROMISE}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={submitGuideProforma} className="flex flex-col gap-5">
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
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
                  placeholder="Choose your grade"
                  options={toOptions(GUIDE_GRADES)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="institution">Institution or trust</Label>
                <Input
                  id="institution"
                  name="institution"
                  required
                  defaultValue={profile.university ?? ""}
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="specialties">
                Specialty interests (up to {MAX_GUIDE_SPECIALTIES},
                comma-separated)
              </Label>
              <Input
                id="specialties"
                name="specialties"
                placeholder="e.g. Cardiology, Emergency medicine"
                defaultValue={profile.specialty ?? ""}
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="specialtyUndecided"
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                Undecided, recommend a field that suits my interests
              </label>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="topics">Topic areas of interest</Label>
              <Textarea
                id="topics"
                name="topics"
                required
                rows={4}
                maxLength={TOPIC_MAX_CHARS}
                placeholder="A condition, a population, a treatment, a question that has bothered you on the ward"
              />
              <p className="text-xs text-muted-foreground">
                Up to {TOPIC_MAX_CHARS} characters.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="publicationType">
                  Type of publication wanted
                </Label>
                <Select
                  id="publicationType"
                  name="publicationType"
                  required
                  placeholder="Choose a type"
                  options={toOptions(PUBLICATION_TYPES)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="existingTitle">
                  Already have a title in mind? (optional)
                </Label>
                <Input id="existingTitle" name="existingTitle" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="hoursPerWeek">Hours available per week</Label>
                <Select
                  id="hoursPerWeek"
                  name="hoursPerWeek"
                  required
                  placeholder="Choose"
                  options={toOptions(HOURS_OPTIONS)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="timeline">Target timeline</Label>
                <Select
                  id="timeline"
                  name="timeline"
                  required
                  placeholder="Choose"
                  options={toOptions(TIMELINE_OPTIONS)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="statsConfidence">Statistical confidence</Label>
                <Select
                  id="statsConfidence"
                  name="statsConfidence"
                  required
                  placeholder="Choose"
                  options={toOptions(STATS_OPTIONS)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="supervisor">
                  Do you already have a supervisor?
                </Label>
                <Select
                  id="supervisor"
                  name="supervisor"
                  required
                  placeholder="Choose"
                  options={toOptions(SUPERVISOR_OPTIONS)}
                />
              </div>
            </div>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Database access</legend>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {DATABASE_OPTIONS.map((d) => (
                  <label key={d} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      name="databases"
                      value={d}
                      className="h-4 w-4 rounded border-input accent-primary"
                    />
                    {d}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-2">
              <Label htmlFor="collaborators">
                How many other people are you comfortable involving in this
                project?
              </Label>
              <Select
                id="collaborators"
                name="collaborators"
                required
                placeholder="Choose"
                options={toOptions(COLLABORATOR_OPTIONS)}
              />
              <p className="text-xs text-muted-foreground">{COLLABORATOR_HELP}</p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="patientData">
                  Do you have access to a patient population or department
                  dataset?
                </Label>
                <Select
                  id="patientData"
                  name="patientData"
                  required
                  placeholder="Choose"
                  options={toOptions(YES_NO_OPTIONS)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="nonEnglish">
                  Can you work with non-English language papers?
                </Label>
                <Select
                  id="nonEnglish"
                  name="nonEnglish"
                  required
                  placeholder="Choose"
                  options={toOptions(YES_NO_OPTIONS)}
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="anythingElse">
                Anything else we should know (optional)
              </Label>
              <Textarea id="anythingElse" name="anythingElse" rows={3} />
            </div>

            <Button type="submit" className="mt-2 self-start">
              Review and continue
            </Button>
            <p className="text-xs text-muted-foreground">
              Next you&apos;ll see a summary of your request and the price
              before deciding whether to pay.
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
