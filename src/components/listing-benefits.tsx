import { BENEFITS_AVAILABILITY_NOTE, LISTING_BENEFITS } from "@/lib/guides-meta";

// Amendment §8.1/§8.2 — the "list your project" benefits, shown on the guides
// page, in the delivered guide and on the confirmation page. Lead phrase bold,
// explanation normal weight. §8.7 makes clear benefits follow from posting.
export function ListingBenefits({
  heading = "List your project, and we help you lead it",
  className = "",
}: {
  heading?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <h2 className="font-heading text-2xl font-semibold tracking-tight">
        {heading}
      </h2>
      <ul className="mt-6 grid gap-x-10 gap-y-4 sm:grid-cols-2">
        {LISTING_BENEFITS.map(([lead, rest]) => (
          <li key={lead} className="text-sm leading-relaxed">
            <strong className="font-semibold text-foreground">{lead}</strong>{" "}
            <span className="text-muted-foreground">{rest}</span>
          </li>
        ))}
      </ul>
      <p className="mt-5 text-sm text-muted-foreground">
        {BENEFITS_AVAILABILITY_NOTE}
      </p>
    </div>
  );
}
