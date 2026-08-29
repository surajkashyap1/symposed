import Link from "next/link";
import { Bell, ClipboardList, LayoutDashboard, Plus } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { signOut } from "@/app/auth/actions";
import { getUnreadNotificationCount } from "@/lib/queries/notifications";
import { Button, buttonVariants } from "@/components/ui/button";
import { LogoLockup } from "@/components/logo";

// Four core destinations (spec §6.1): Projects (the board), People
// (/available), Guides (revenue product), Teaching. Everything else is an
// icon or lives in the footer to keep the bar breathable.
const DESTINATIONS = [
  { href: "/projects", label: "Projects" },
  { href: "/available", label: "People" },
  { href: "/guides", label: "Guides" },
  { href: "/teach", label: "Teaching" },
] as const;

export async function SiteHeader() {
  const user = await getSessionUser();
  const unreadNotifications = user
    ? await getUnreadNotificationCount(user.id)
    : 0;

  return (
    <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between gap-3 px-6">
        <Link href="/" className="shrink-0 transition-opacity hover:opacity-70">
          <LogoLockup />
        </Link>
        <nav className="flex items-center gap-1 overflow-x-auto overflow-y-hidden py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0">
          {DESTINATIONS.map((d) => (
            <Link
              key={d.href}
              href={d.href}
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              {d.label}
            </Link>
          ))}
          {user ? (
            <>
              <Link
                href="/applications"
                aria-label="My applications"
                title="My applications"
                className={buttonVariants({ variant: "ghost", size: "icon" })}
              >
                <ClipboardList className="size-4.5" aria-hidden />
              </Link>
              <Link
                href="/notifications"
                aria-label={`Notifications${unreadNotifications > 0 ? ` (${unreadNotifications} unread)` : ""}`}
                title="Notifications"
                className={`relative ${buttonVariants({ variant: "ghost", size: "icon" })}`}
              >
                <Bell className="size-4.5" aria-hidden />
                {unreadNotifications > 0 && (
                  <span
                    aria-hidden
                    className="absolute right-1 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground"
                  >
                    {unreadNotifications > 9 ? "9+" : unreadNotifications}
                  </span>
                )}
              </Link>
              <Link
                href="/dashboard"
                aria-label="Dashboard"
                title="Dashboard"
                className={buttonVariants({ variant: "ghost", size: "icon" })}
              >
                <LayoutDashboard className="size-4.5" aria-hidden />
              </Link>
              <Link
                href="/projects/new"
                className={buttonVariants({ size: "sm", className: "ml-1 gap-1" })}
              >
                <Plus className="size-3.5" aria-hidden />
                Post a project
              </Link>
              <form action={signOut}>
                <Button variant="outline" size="sm" type="submit">
                  Sign out
                </Button>
              </form>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className={buttonVariants({ variant: "default", size: "sm" })}
              >
                Get started
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
