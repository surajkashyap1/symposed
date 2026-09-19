import { requireAdmin } from "@/lib/auth";
import { getAttributionReport, type DateRange } from "@/lib/queries/attribution";
import { createReferralCode } from "@/app/admin/attribution/actions";
import { AdminNav } from "@/components/admin-nav";
import { CopyLinkButton } from "@/components/copy-link-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Attribution admin | Symposed" };
export const dynamic = "force-dynamic";

// A conversion rate as a percentage of the previous step, or a dash when the
// denominator is zero (a rate is meaningless with nothing to convert).
function pct(numerator: number, denominator: number): string {
  if (denominator <= 0) return "-"; // plain hyphen = no data (spec §11: no en/em dashes)
  return `${Math.round((numerator / denominator) * 100)}%`;
}

// Parse a yyyy-mm-dd input into an explicit UTC instant, so the window is the
// same whatever timezone the server runs in. `endOfDay` includes the whole
// "to" day rather than cutting it off at midnight.
function parseDate(v: string | undefined, endOfDay = false): Date | undefined {
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return undefined;
  const d = new Date(`${v}T${endOfDay ? "23:59:59.999" : "00:00:00.000"}Z`);
  return Number.isNaN(d.getTime()) ? undefined : d;
}

export default async function AdminAttributionPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; to?: string; error?: string }>;
}) {
  await requireAdmin();
  const { from, to, error } = await searchParams;

  const range: DateRange = {
    from: parseDate(from),
    to: parseDate(to, true),
  };

  const report = await getAttributionReport(range);
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  const codes = report.filter((r) => r.label !== null);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      <AdminNav current="attribution" />
      <h1 className="mt-6 font-serif text-2xl">Channel attribution</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
        Where signups come from and how each channel converts through the
        funnel. First touch wins, and an unknown or missing code is recorded as
        direct.
      </p>

      {error && (
        <p className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* Date filter (§9.2) */}
      <form method="get" className="mt-6 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="from">From</Label>
          <Input id="from" type="date" name="from" defaultValue={from} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="to">To</Label>
          <Input id="to" type="date" name="to" defaultValue={to} />
        </div>
        <Button type="submit" variant="outline">
          Apply
        </Button>
        {(from || to) && (
          <a
            href="/admin/attribution"
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            Clear
          </a>
        )}
      </form>

      {/* Funnel report (§9.2): conversion at each step, not just totals. */}
      <Card className="mt-6">
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Code</th>
                <th className="px-3 py-3 text-right font-medium">Visits</th>
                <th className="px-3 py-3 text-right font-medium">Signups</th>
                <th className="px-3 py-3 text-right font-medium">Requests</th>
                <th className="px-3 py-3 text-right font-medium">Delivered</th>
                <th className="px-3 py-3 text-right font-medium">Listings</th>
                <th className="px-4 py-3 text-right font-medium">
                  Signup / request rate
                </th>
              </tr>
            </thead>
            <tbody>
              {report.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-muted-foreground">
                    No activity in this range yet.
                  </td>
                </tr>
              )}
              {report.map((r) => (
                <tr key={r.code} className="border-b last:border-0">
                  <td className="px-4 py-3">
                    <span className="font-medium">{r.code}</span>
                    {r.label && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {r.label}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.visits}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.signups}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.requests}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.delivered}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.listings}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                    {pct(r.signups, r.visits)} / {pct(r.requests, r.signups)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <p className="mt-2 text-xs text-muted-foreground">
        Signup rate is signups per visit; request rate is guide requests per
        signup. A channel bringing many signups and no requests is worth less
        than a smaller one that converts.
      </p>

      {/* Code management (§9.3) */}
      <Card className="mt-8">
        <CardHeader>
          <CardTitle className="text-base">Referral codes</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Issue a distinct code to every individual influencer, society or
            institution. Never a shared code, since a shared one teaches nothing
            about which of them works.
          </p>

          {codes.length > 0 && (
            <ul className="flex flex-col divide-y rounded-md border">
              {codes.map((c) => {
                const link = `${base}/guides?ref=${c.code}`;
                return (
                  <li
                    key={c.code}
                    className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="font-medium">
                        {c.code}
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          {c.label}
                        </span>
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {link}
                      </p>
                    </div>
                    <CopyLinkButton value={link} />
                  </li>
                );
              })}
            </ul>
          )}

          <form
            action={createReferralCode}
            className="flex flex-wrap items-end gap-3 border-t pt-4"
          >
            <div className="grid gap-1.5">
              <Label htmlFor="code">New code</Label>
              <Input
                id="code"
                name="code"
                placeholder="manchester"
                pattern="[a-z0-9-]+"
                required
              />
            </div>
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor="label">Label</Label>
              <Input
                id="label"
                name="label"
                placeholder="University of Manchester society"
                required
              />
            </div>
            <Button type="submit">Create code</Button>
          </form>
          <p className="text-xs text-muted-foreground">
            Lowercase letters, numbers and hyphens only. No personal data in the
            code itself.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
