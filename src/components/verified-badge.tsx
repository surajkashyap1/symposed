import { BadgeCheck } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The verified marker, used wherever a name appears. A filled seal icon in the
 * success role — reads as a credential, unlike the old bare "✓" text glyph.
 */
export function VerifiedMark({ className }: { className?: string }) {
  return (
    <span
      title="Verified — confirmed a university or health-service email"
      className={cn("inline-flex shrink-0 items-center text-success", className)}
    >
      <BadgeCheck className="size-[1.1em]" aria-hidden />
      <span className="sr-only">Verified</span>
    </span>
  );
}

/** Pill form for surfaces that list statuses (dashboard, profile header). */
export function VerifiedPill() {
  return (
    <span className="inline-flex h-5 w-fit items-center gap-1 rounded-4xl border border-success/30 bg-success/10 px-2 text-xs font-medium text-success">
      <BadgeCheck className="size-3" aria-hidden />
      Verified
    </span>
  );
}

/**
 * Verified supervisor: a verified health-service account eligible to
 * supervise. Shown beside lister names so applicants can spot a supervisor-led
 * project at a glance.
 */
export function SupervisorPill() {
  return (
    <span
      title="Verified supervisor — a verified healthcare professional eligible to supervise projects"
      className="inline-flex h-5 w-fit items-center gap-1 rounded-4xl border border-success/30 bg-success/10 px-2 text-xs font-medium text-success"
    >
      <BadgeCheck className="size-3" aria-hidden />
      Verified supervisor
    </span>
  );
}
