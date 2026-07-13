import Link from "next/link";
import { LogoMark } from "@/components/logo";

const LINKS = [
  { href: "/about", label: "About" },
  { href: "/guide", label: "How it works" },
  { href: "/contact", label: "Contact" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
  { href: "/cookies", label: "Cookies" },
  { href: "/policies", label: "All policies" },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-ink-foreground/10 bg-ink text-ink-foreground/75">
      <div className="mx-auto flex w-full max-w-5xl flex-col items-center justify-between gap-3 px-6 py-6 text-sm sm:flex-row">
        <p className="flex items-center gap-2">
          <LogoMark height={16} className="text-ink-foreground" />
          <span>
            <span className="font-heading font-semibold text-ink-foreground">
              Symposed
            </span>{" "}
            · Bringing research to you.
          </span>
        </p>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="hover:text-ink-foreground"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
