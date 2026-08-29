import Link from "next/link";
import { CalendarDays, Clock3, MapPin } from "lucide-react";
import { CAREER_STAGES } from "@/lib/profile";
import { listingDisplayName } from "@/lib/board-meta";
import { formatDateUK } from "@/lib/utils";
import type { AvailabilityListItem } from "@/lib/queries/availability";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { VerifiedMark } from "@/components/verified-badge";

const SKILLS_SHOWN = 5;

function stageLabel(value: string | null) {
  if (!value) return null;
  return CAREER_STAGES.find((s) => s.value === value)?.label ?? value;
}

export function AvailabilityCard({ l }: { l: AvailabilityListItem }) {
  const name = listingDisplayName(l.ownerName ?? "Anonymous", l.displayInitialsOnly);
  const meta = [
    stageLabel(l.ownerCareerStage),
    l.showInstitution ? l.ownerUniversity : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const extraSkills = l.skills.length - SKILLS_SHOWN;

  return (
    <article className="flex flex-col rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-medium text-card-foreground">
            {name}
            {l.ownerVerified && <VerifiedMark />}
          </p>
          {meta && <p className="mt-0.5 text-xs text-muted-foreground">{meta}</p>}
        </div>
        {l.region && (
          <span className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="h-3.5 w-3.5" aria-hidden />
            {l.region}
          </span>
        )}
      </div>

      <h3 className="mt-3 break-words font-semibold leading-snug text-card-foreground">
        {l.headline}
      </h3>
      <p className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">
        {l.lookingFor}
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {l.skills.slice(0, SKILLS_SHOWN).map((s) => (
          <Badge key={s} variant="secondary">
            {s}
          </Badge>
        ))}
        {extraSkills > 0 && <Badge variant="outline">+{extraSkills} more</Badge>}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {l.hoursPerWeek != null && (
          <span className="inline-flex items-center gap-1">
            <Clock3 className="h-3.5 w-3.5" aria-hidden />
            {l.hoursPerWeek} hrs/week
          </span>
        )}
        {l.availableFrom && (
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-3.5 w-3.5" aria-hidden />
            From {formatDateUK(l.availableFrom)}
          </span>
        )}
        {l.specialties && <span>{l.specialties}</span>}
      </div>

      {l.previousPublications && (
        <p className="mt-2 line-clamp-1 text-xs text-muted-foreground">
          Publications: {l.previousPublications}
        </p>
      )}

      <div className="mt-4 flex items-center justify-between gap-2 border-t pt-4">
        <Link
          href={`/profile/${l.profileId}`}
          className="text-sm text-primary hover:underline"
        >
          View profile
        </Link>
        <Link
          href={`/available/${l.id}/contact`}
          className={buttonVariants({ size: "sm" })}
        >
          Get in touch
        </Link>
      </div>
    </article>
  );
}
