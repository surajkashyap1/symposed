import Link from "next/link";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { key: "overview", label: "Overview", href: "/admin" },
  { key: "guides", label: "Guides", href: "/admin/guides" },
  { key: "teaching", label: "Teaching", href: "/admin/teaching" },
  { key: "listings", label: "Listings", href: "/admin/listings" },
  { key: "attribution", label: "Attribution", href: "/admin/attribution" },
] as const;

export function AdminNav({ current }: { current: (typeof SECTIONS)[number]["key"] }) {
  return (
    <nav className="flex flex-wrap gap-1.5 border-b pb-3">
      {SECTIONS.map((s) => (
        <Link
          key={s.key}
          href={s.href}
          className={cn(
            "rounded-md px-2.5 py-1 text-sm font-medium",
            s.key === current
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
          )}
        >
          {s.label}
        </Link>
      ))}
    </nav>
  );
}
