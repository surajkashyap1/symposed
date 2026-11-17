import { BookOpen, Mail, Search } from "lucide-react";
import {
  OPEN_GUIDES_EMAIL,
  openGuideMailto,
  openGuideTitle,
  openGuideTypeLabel,
} from "@/lib/open-guides-meta";
import type { OpenGuide } from "@/lib/queries/open-guides";
import { buttonVariants } from "@/components/ui/button";

// One ready-made guide on the open guides board. The title is generic on
// purpose: the research question is only shared with the buyer.
export function OpenGuideCard({ g }: { g: OpenGuide }) {
  const TypeIcon = g.reviewType === "systematic_review" ? Search : BookOpen;
  return (
    <div className="flex flex-col rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 break-words font-semibold leading-snug text-card-foreground">
          {openGuideTitle(g)}
        </h3>
        <span className="shrink-0 text-xs text-muted-foreground">{g.reference}</span>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary">
          <TypeIcon className="h-3.5 w-3.5" aria-hidden />
          {openGuideTypeLabel(g.reviewType)}
        </span>
        <span className="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium text-muted-foreground">
          {g.specialty}
        </span>
      </div>
      <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
        {g.description}
      </p>
      <div className="mt-auto pt-4">
        <a
          href={openGuideMailto(g)}
          className={buttonVariants({ size: "sm", className: "gap-1.5" })}
        >
          <Mail className="h-3.5 w-3.5" aria-hidden />
          Email to buy this guide
        </a>
        <p className="mt-2 text-xs text-muted-foreground">
          Or email{" "}
          <a href={`mailto:${OPEN_GUIDES_EMAIL}`} className="font-medium text-primary hover:underline">
            {OPEN_GUIDES_EMAIL}
          </a>{" "}
          quoting {g.reference}.
        </p>
      </div>
    </div>
  );
}
