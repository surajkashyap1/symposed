import { requireUser, ensureProfile } from "@/lib/auth";
import { getMyListing } from "@/lib/queries/availability";
import {
  HEADLINE_MAX_CHARS,
  LOOKING_FOR_MAX_CHARS,
  SKILLS_OFFERED,
} from "@/lib/board-meta";
import { upsertListing } from "@/app/available/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Advertise yourself — Symposed" };

export default async function NewListingPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const user = await requireUser();
  await ensureProfile(user);
  const [{ error }, existing] = await Promise.all([
    searchParams,
    getMyListing(user.id),
  ]);

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>{existing ? "Edit your listing" : "Advertise yourself"}</CardTitle>
          <CardDescription>
            Tell listers what you can offer and what you&apos;re looking for.
            You have one listing; saving replaces it and puts it live for 60
            days. Free, always.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={upsertListing} className="flex flex-col gap-5">
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="headline">Headline</Label>
              <Input
                id="headline"
                name="headline"
                required
                maxLength={HEADLINE_MAX_CHARS}
                placeholder='e.g. "F2 in Manchester looking to join a systematic review"'
                defaultValue={existing?.headline ?? ""}
              />
              <p className="text-xs text-muted-foreground">
                One sentence, up to {HEADLINE_MAX_CHARS} characters. This is the
                first thing listers read.
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="lookingFor">What I am looking for</Label>
              <Textarea
                id="lookingFor"
                name="lookingFor"
                required
                rows={4}
                maxLength={LOOKING_FOR_MAX_CHARS}
                placeholder="The kind of project you want to join, what you can commit to, and anything a lister should know."
                defaultValue={existing?.lookingFor ?? ""}
              />
            </div>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Skills offered</legend>
              <p className="text-xs text-muted-foreground">
                Pick everything you can genuinely do — listers filter by these.
              </p>
              <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                {SKILLS_OFFERED.map((s) => (
                  <label
                    key={s}
                    className="flex items-center gap-2 text-sm text-foreground"
                  >
                    <input
                      type="checkbox"
                      name="skills"
                      value={s}
                      defaultChecked={existing?.skills.includes(s) ?? false}
                      className="h-4 w-4 rounded border-input accent-primary"
                    />
                    {s}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-2">
              <Label htmlFor="specialties">
                Specialty interests (up to 3, comma-separated)
              </Label>
              <Input
                id="specialties"
                name="specialties"
                placeholder="e.g. Cardiology, Public health"
                defaultValue={existing?.specialties ?? ""}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="hoursPerWeek">Hours per week</Label>
                <Input
                  id="hoursPerWeek"
                  name="hoursPerWeek"
                  type="number"
                  min="0"
                  max="80"
                  step="1"
                  placeholder="e.g. 5"
                  defaultValue={existing?.hoursPerWeek ?? ""}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="availableFrom">Available from</Label>
                <Input
                  id="availableFrom"
                  name="availableFrom"
                  type="date"
                  defaultValue={existing?.availableFrom ?? ""}
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="region">Location or region</Label>
              <Input
                id="region"
                name="region"
                placeholder="e.g. Manchester, North West, Remote"
                defaultValue={existing?.region ?? ""}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="previousPublications">
                Previous publications (optional)
              </Label>
              <Input
                id="previousPublications"
                name="previousPublications"
                placeholder="A count, or links — e.g. 2 (PubMed: …)"
                defaultValue={existing?.previousPublications ?? ""}
              />
            </div>

            <fieldset className="grid gap-2 rounded-md border bg-muted/20 p-3">
              <legend className="px-1 text-sm font-medium">Privacy</legend>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="displayInitialsOnly"
                  defaultChecked={existing?.displayInitialsOnly ?? false}
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                Show my initials instead of my full name on the board
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="showInstitution"
                  defaultChecked={existing?.showInstitution ?? true}
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                Show my institution
              </label>
              <p className="text-xs text-muted-foreground">
                Your email address is never shown. People contact you through
                Symposed and you choose whether to reply.
              </p>
            </fieldset>

            <Button type="submit" className="mt-2 self-start">
              {existing ? "Save and republish" : "Publish listing"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
