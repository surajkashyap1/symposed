import Link from "next/link";
import { requireUser, ensureProfile } from "@/lib/auth";
import { getProjectRecord } from "@/lib/queries/member";
import { PrintButton } from "@/components/print-button";
import { buttonVariants } from "@/components/ui/button";

export const metadata = { title: "Your track record | Symposed" };

const STATUS_LABEL: Record<string, string> = {
  open: "Recruiting",
  in_progress: "In progress",
  completed: "Completed",
  closed: "Closed",
};

function dateUK(d: Date) {
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

// Amendment §8.3 — an exportable summary the user can download as a PDF. It
// states only what happened: the project existed, who led it, how many joined
// and when. It never characterises the quality of the work and never uses the
// phrase "portfolio points".
export default async function ProfileRecordPage() {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const record = await getProjectRecord(user.id);

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10 print:py-4">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <Link
          href="/dashboard"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back to dashboard
        </Link>
        <PrintButton />
      </div>

      <header className="mt-6 border-b pb-4">
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Symposed track record
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {profile.fullName}
          {profile.university ? ` · ${profile.university}` : ""} · generated{" "}
          {dateUK(new Date())}
        </p>
      </header>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Projects led ({record.led.length})
        </h2>
        {record.led.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            No projects led yet.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {record.led.map((p) => (
              <li key={p.id} className="border-b pb-3 last:border-b-0">
                <p className="font-medium">{p.title}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {STATUS_LABEL[p.status] ?? p.status} · started {dateUK(p.createdAt)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Collaborators recruited through Symposed
        </h2>
        <p className="mt-2 text-2xl font-semibold tabular-nums">
          {record.collaboratorsRecruited}
        </p>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Projects joined as a collaborator ({record.joined.length})
        </h2>
        {record.joined.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            No projects joined yet.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {record.joined.map((p) => (
              <li key={p.id} className="border-b pb-3 last:border-b-0">
                <p className="font-medium">{p.title}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {STATUS_LABEL[p.status] ?? p.status} · joined {dateUK(p.createdAt)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="mt-8 border-t pt-4 text-xs leading-relaxed text-muted-foreground">
        Symposed confirms what happened: that the project existed, who led it,
        how many people joined and when. It does not characterise the quality of
        the work, and how any of it is assessed is determined by your
        specialty&apos;s published criteria, which you must check yourself.
      </footer>
    </main>
  );
}
