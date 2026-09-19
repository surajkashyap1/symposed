import Link from "next/link";
import { Download, FileText } from "lucide-react";
import { requireUser } from "@/lib/auth";
import { listOrdersForUser, listOrderFiles } from "@/lib/queries/guides";
import { getListingForOrder } from "@/lib/guide-listing";
import { DELIVERY_PROMISE, formatPounds } from "@/lib/guides-meta";
import { GuideListingPanel } from "@/components/guide-listing-panel";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const metadata = { title: "My guides | Symposed" };

const STATUS_LABELS: Record<string, string> = {
  submitted: "Awaiting payment",
  paid: "In the queue",
  in_progress: "Being researched",
  delivered: "Delivered",
  refunded: "Refunded",
};

const STATUS_CLASS: Record<string, string> = {
  delivered: "border-transparent bg-success text-success-foreground",
  refunded: "bg-secondary text-secondary-foreground",
};

export default async function MyGuidesPage({
  searchParams,
}: {
  searchParams: Promise<{
    error?: string;
    draftSaved?: string;
    draftRegenerated?: string;
    regenerate?: string;
  }>;
}) {
  const user = await requireUser();
  const { error, draftSaved, draftRegenerated, regenerate } = await searchParams;
  const orders = await listOrdersForUser(user.id);
  const delivered = orders.filter((o) => o.status === "delivered");
  const [filesByOrder, listingByOrder] = await Promise.all([
    Promise.all(
      delivered.map(async (o) => [o.id, await listOrderFiles(o.id)] as const)
    ).then((e) => new Map(e)),
    Promise.all(
      delivered.map(async (o) => [o.id, await getListingForOrder(o.id)] as const)
    ).then((e) => new Map(e)),
  ]);

  const flash = draftSaved
    ? "Draft saved."
    : draftRegenerated
      ? "Draft listing regenerated from your guide."
      : null;

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">My guides</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Your bespoke research guides. Downloads never expire, your account is
        the licence.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {flash && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          {flash}
        </div>
      )}

      {orders.length === 0 ? (
        <div className="mt-10 rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          <p>No guides yet.</p>
          <Link
            href="/guides"
            className={buttonVariants({ size: "sm", className: "mt-4" })}
          >
            See what a guide includes
          </Link>
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {orders.map((o) => {
            const files = filesByOrder.get(o.id) ?? [];
            return (
              <Card key={o.id}>
                <CardContent>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium">
                        Publication Guide
                        {o.pricePaidPence
                          ? `, ${formatPounds(o.pricePaidPence)}`
                          : ""}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Ordered {o.createdAt.toLocaleDateString("en-GB")}
                        {o.deliveredAt &&
                          ` · delivered ${o.deliveredAt.toLocaleDateString("en-GB")}`}
                      </p>
                    </div>
                    <Badge
                      variant="secondary"
                      className={STATUS_CLASS[o.status] ?? ""}
                    >
                      {STATUS_LABELS[o.status] ?? o.status}
                    </Badge>
                  </div>

                  {o.status === "submitted" && (
                    <Link
                      href={`/guides/checkout?order=${o.id}`}
                      className={buttonVariants({ size: "sm", className: "mt-4" })}
                    >
                      Complete your order
                    </Link>
                  )}

                  {(o.status === "paid" || o.status === "in_progress") && (
                    <p className="mt-3 text-sm text-muted-foreground">
                      {DELIVERY_PROMISE} We&apos;ll email you the moment
                      it&apos;s ready.
                    </p>
                  )}

                  {o.status === "delivered" && files.length > 0 && (
                    <ul className="mt-4 flex flex-col gap-2">
                      {files.map((f) => (
                        <li key={f.id}>
                          <a
                            href={`/guides/download/${f.id}`}
                            className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium hover:border-primary/40 hover:bg-accent/40"
                          >
                            <FileText
                              className="h-4 w-4 text-muted-foreground"
                              aria-hidden
                            />
                            {f.filename}
                            <Download
                              className="ml-1 h-3.5 w-3.5 text-muted-foreground"
                              aria-hidden
                            />
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}

                  {o.status === "delivered" && (
                    <GuideListingPanel
                      orderId={o.id}
                      listing={listingByOrder.get(o.id) ?? null}
                      offerRegenerate={regenerate === o.id}
                    />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </main>
  );
}
