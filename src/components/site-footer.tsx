import Link from "next/link";

const LINKS = [
  { href: "/about", label: "About" },
  { href: "/ethos", label: "Ethos & usage" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
];

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-5xl flex-col items-center justify-between gap-3 px-6 py-6 text-sm text-muted-foreground sm:flex-row">
        <p>
          <span className="font-heading font-semibold text-foreground">
            Symposed
          </span>{" "}
          · Bringing research to you.
        </p>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-foreground">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
