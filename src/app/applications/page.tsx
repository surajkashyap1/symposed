import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { getApplicationsByApplicant, getApplicationAllowance } from "@/lib/queries/applications";
import { STATUS_LABELS, STATUS_BADGE_CLASS } from "@/lib/application-meta";
import { withdrawApplication } from "@/app/applications/actions";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ContactDetails } from "@/components/contact-details";

export default async function ApplicationsPage() {
  const user = await requireUser();
  const [apps, allowance] = await Promise.all([
    getApplicationsByApplicant(user.id),
    getApplicationAllowance(user.id),
  ]);

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">My applications</h1>

      <Card className="mt-6">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <div>
            <span className="font-semibold">{allowance.remaining}</span> of{" "}
            <span className="font-semibold">{allowance.limit}</span> applications
            left this week
            {allowance.bonus && (
              <Badge variant="outline" className="ml-2">
                +{allowance.limit - 3} lister bonus
              </Badge>
            )}
          </div>
          {allowance.remaining === 0 && allowance.resetsAt && (
            <span className="text-muted-foreground">
              Resets {allowance.resetsAt.toLocaleDateString("en-GB")}
            </span>
          )}
        </CardContent>
      </Card>

      {apps.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">
            You haven&apos;t applied to any projects yet.
          </p>
          <Link href="/projects" className={`mt-4 ${buttonVariants()}`}>
            Browse projects
          </Link>
        </div>
      ) : (
        <ul className="mt-8 flex flex-col gap-3">
          {apps.map((a) => (
            <li
              key={a.id}
              className="flex flex-col gap-4 rounded-lg border p-4"
            >
              <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <Link
                  href={`/projects/${a.projectId}`}
                  className="font-medium hover:underline"
                >
                  {a.projectTitle}
                </Link>
                <p className="mt-1 text-xs text-muted-foreground">
                  {a.projectTypeLabel} · applied{" "}
                  {a.createdAt.toLocaleDateString("en-GB")}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <Badge className={STATUS_BADGE_CLASS[a.status]}>
                  {STATUS_LABELS[a.status]}
                </Badge>
                {a.status === "pending" && (
                  <form action={withdrawApplication}>
                    <input type="hidden" name="id" value={a.id} />
                    <Button type="submit" variant="ghost" size="sm">
                      Withdraw
                    </Button>
                  </form>
                )}
                {a.status === "accepted" && (
                  <Link
                    href={`/projects/${a.projectId}/review/${a.projectOwnerId}`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    Review supervisor
                  </Link>
                )}
              </div>
              </div>
              {a.status === "accepted" && a.listerEmail && (
                <ContactDetails
                  heading={`${a.listerName ?? "The project lister"}'s contact details`}
                  email={a.listerEmail}
                  phone={a.listerPhone}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
