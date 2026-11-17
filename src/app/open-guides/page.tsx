import Link from "next/link";
import { Mail } from "lucide-react";
import {
  OPEN_GUIDES_EMAIL,
  OPEN_GUIDE_TYPES,
  OPEN_GUIDE_TYPE_VALUES,
  type OpenGuideType,
} from "@/lib/open-guides-meta";
import { listAvailableOpenGuides } from "@/lib/queries/open-guides";
import { OpenGuideCard } from "@/components/open-guide-card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Open project guides | Symposed",
  description:
    "Ready-made Publication Guides for systematic and literature reviews, listed by specialty. Email us to buy one.",
};

type SP = { specialty?: string; type?: string };

export default async function OpenGuidesPage({
  searchParams,
}: {
  searchParams: Promise<SP>;
}) {
  const sp = await searchParams;
  const specialty = sp.specialty?.trim() || undefined;
  const type = OPEN_GUIDE_TYPE_VALUES.has(sp.type ?? "")
    ? (sp.type as OpenGuideType)
    : undefined;
  const guides = await listAvailableOpenGuides({ specialty, type });
  const filtered = Boolean(specialty || type);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Open project guides</h1>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Complete Publication Guides we have already made, ready to start now.
        Each one is listed by specialty and review type only, so its research
        question stays private until you buy it.
      </p>

      <div className="mt-5 max-w-2xl rounded-lg border bg-secondary/50 px-5 py-4 text-sm leading-relaxed">
        <p className="font-semibold">How to buy one</p>
        <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-muted-foreground">
          <li>Choose a guide below and note its reference.</li>
          <li>
            Email{" "}
            <a
              href={`mailto:${OPEN_GUIDES_EMAIL}`}
              className="font-medium text-primary hover:underline"
            >
              {OPEN_GUIDES_EMAIL}
            </a>{" "}
            quoting the reference. We will reply with the price and how to pay.
          </li>
          <li>
            We check again that the question is still new, then send you the
            guide. Each guide is sold once and comes off this page when it is.
          </li>
        </ol>
      </div>

      {/* Filters (GET form) */}
      <form className="mt-6 grid gap-3 sm:grid-cols-3">
        <Input name="specialty" placeholder="Specialty" defaultValue={specialty ?? ""} />
        <Select
          name="type"
          defaultValue={type ?? ""}
          options={[{ value: "", label: "Any review type" }, ...OPEN_GUIDE_TYPES]}
        />
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>

      {guides.length === 0 ? (
        <div className="mt-12 rounded-lg border border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">
            {filtered
              ? "No open guides match. Try clearing the filters."
              : "No open guides are available right now. Check back soon."}
          </p>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {guides.map((g) => (
            <OpenGuideCard key={g.id} g={g} />
          ))}
        </div>
      )}

      <div className="mt-10 flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-lg border bg-secondary/50 px-5 py-4 text-sm">
        <Mail className="h-4 w-4 text-muted-foreground" aria-hidden />
        Want a guide built around your own specialty and topic?{" "}
        <Link href="/guides" className="font-medium text-primary hover:underline">
          Request a bespoke guide
        </Link>
        .
      </div>
    </main>
  );
}
