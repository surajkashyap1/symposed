import Link from "next/link";
import { requireAdmin } from "@/lib/auth";
import {
  createOpenGuide,
  deleteOpenGuide,
  setOpenGuideAvailable,
} from "@/app/admin/open-guides/actions";
import {
  OPEN_GUIDE_DESCRIPTION_MAX,
  OPEN_GUIDE_SPECIALTY_MAX,
  OPEN_GUIDE_TYPES,
  OPEN_GUIDES_EMAIL,
  openGuideTitle,
} from "@/lib/open-guides-meta";
import { listAllOpenGuides } from "@/lib/queries/open-guides";
import { AdminNav } from "@/components/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export const metadata = { title: "Open guides admin | Symposed" };

export default async function AdminOpenGuidesPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; added?: string }>;
}) {
  await requireAdmin();
  const { error, added } = await searchParams;
  const guides = await listAllOpenGuides();

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <AdminNav current="open-guides" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">Open project guides</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Ready-made guides listed on{" "}
        <Link href="/open-guides" className="text-primary hover:underline">
          /open-guides
        </Link>
        . Buyers email {OPEN_GUIDES_EMAIL} quoting the reference. The public
        title is only the specialty and review type, so never put the research
        question, or anything that gives it away, in the description.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {added && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          Guide listed.
        </div>
      )}

      {guides === null ? (
        <div className="mt-6 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          The open_guides table does not exist yet. Apply the migration with{" "}
          <code>npm run db:migrate</code>, then run{" "}
          <code>node scripts/apply-sql.mjs drizzle/manual/0004_enable_rls.sql</code>.
        </div>
      ) : (
        <>
          <h2 className="mt-8 text-lg font-semibold tracking-tight">List a guide</h2>
          <form
            action={createOpenGuide}
            className="mt-3 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-2"
          >
            <div className="grid gap-1.5">
              <Label htmlFor="specialty">Specialty</Label>
              <Input
                id="specialty"
                name="specialty"
                required
                maxLength={OPEN_GUIDE_SPECIALTY_MAX}
                placeholder="e.g. Rheumatology"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="reviewType">Review type</Label>
              <Select
                id="reviewType"
                name="reviewType"
                required
                defaultValue="systematic_review"
                options={[...OPEN_GUIDE_TYPES]}
              />
            </div>
            <div className="grid gap-1.5 sm:col-span-2">
              <Label htmlFor="description">Public description</Label>
              <Textarea
                id="description"
                name="description"
                rows={3}
                required
                maxLength={OPEN_GUIDE_DESCRIPTION_MAX}
                placeholder="e.g. A drug treatment question in an inflammatory joint disease, using real-world registry and cohort studies. Suits a team of 3 to 5 with basic statistics."
              />
            </div>
            <Button type="submit" size="sm" className="self-start">
              List guide
            </Button>
          </form>

          <h2 className="mt-10 text-lg font-semibold tracking-tight">
            Listed guides ({guides.length})
          </h2>
          {guides.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">None yet.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {guides.map((g) => (
                <Card key={g.id}>
                  <CardContent className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{openGuideTitle(g)}</span>
                      <span className="text-xs text-muted-foreground">{g.reference}</span>
                      {g.isAvailable ? (
                        <Badge className="border-transparent bg-success text-success-foreground">
                          Listed
                        </Badge>
                      ) : (
                        <Badge variant="outline">Sold or withdrawn</Badge>
                      )}
                    </div>
                    <p className="whitespace-pre-line text-sm text-muted-foreground">
                      {g.description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <form action={setOpenGuideAvailable}>
                        <input type="hidden" name="id" value={g.id} />
                        <input type="hidden" name="available" value={g.isAvailable ? "0" : "1"} />
                        <Button type="submit" size="sm" variant="outline">
                          {g.isAvailable ? "Mark sold or withdrawn" : "List again"}
                        </Button>
                      </form>
                      <form action={deleteOpenGuide}>
                        <input type="hidden" name="id" value={g.id} />
                        <Button type="submit" size="sm" variant="ghost">
                          Delete
                        </Button>
                      </form>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
