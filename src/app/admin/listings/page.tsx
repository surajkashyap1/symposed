import { desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { availabilityListings, listingContacts, profiles } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { removeListingAdmin } from "@/app/admin/listings/actions";
import { AdminNav } from "@/components/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const metadata = { title: "Listings admin — Symposed" };

export default async function AdminListingsPage() {
  await requireAdmin();

  const [listings, [contactAgg]] = await Promise.all([
    db
      .select({
        listing: availabilityListings,
        ownerName: profiles.fullName,
        ownerEmail: profiles.email,
      })
      .from(availabilityListings)
      .leftJoin(profiles, eq(profiles.id, availabilityListings.profileId))
      .orderBy(desc(availabilityListings.updatedAt))
      .limit(100),
    db
      .select({
        total: sql<number>`count(*)::int`,
        last7d: sql<number>`count(*) filter (where ${listingContacts.createdAt} > now() - interval '7 days')::int`,
      })
      .from(listingContacts),
  ]);

  const found = listings.filter((l) => l.listing.status === "found_project").length;
  const active = listings.filter((l) => l.listing.status === "active").length;

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <AdminNav current="listings" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">
        Availability listings
      </h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-4">
        {[
          ["Listings (all)", listings.length],
          ["Active", active],
          ["Found a project", found],
          ["Contacts sent (7d)", contactAgg.last7d],
        ].map(([label, value]) => (
          <Card key={String(label)}>
            <CardContent>
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        &ldquo;Found a project&rdquo; is the metric that says the board works.
        Total contacts ever sent: {contactAgg.total}.
      </p>

      <div className="mt-6 flex flex-col gap-3">
        {listings.map(({ listing: l, ownerName, ownerEmail }) => (
          <Card key={l.id}>
            <CardContent className="text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">
                  {ownerName} <span className="text-xs text-muted-foreground">({ownerEmail})</span>
                </p>
                <Badge variant="secondary" className="capitalize">
                  {l.status.replace("_", " ")}
                </Badge>
              </div>
              <p className="mt-1">{l.headline}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {l.skills.join(", ")} · updated{" "}
                {l.updatedAt.toLocaleDateString("en-GB")} · expires{" "}
                {l.expiresAt.toLocaleDateString("en-GB")}
              </p>
              {l.status === "active" && (
                <form action={removeListingAdmin} className="mt-3">
                  <input type="hidden" name="id" value={l.id} />
                  <Button type="submit" size="sm" variant="destructive">
                    Remove from board
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
