import Link from "next/link";
import { getSessionUser } from "@/lib/auth";
import { signOut } from "@/app/auth/actions";
import { getUnreadNotificationCount } from "@/lib/queries/notifications";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";

export async function SiteHeader() {
  const user = await getSessionUser();
  const unreadNotifications = user
    ? await getUnreadNotificationCount(user.id)
    : 0;

  return (
    <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-6">
        <Link
          href="/"
          className="shrink-0 font-heading text-xl font-semibold tracking-tight text-foreground transition-opacity hover:opacity-70"
        >
          Symposed
        </Link>
        <nav className="flex items-center gap-1.5 overflow-x-auto overflow-y-hidden py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0">
          <Link
            href="/projects"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Projects
          </Link>
          {user ? (
            <>
              <Link
                href="/applications"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Applications
              </Link>
              <Link
                href="/notifications"
                aria-label={`Notifications${unreadNotifications > 0 ? ` (${unreadNotifications} unread)` : ""}`}
                className={`relative ${buttonVariants({ variant: "ghost", size: "sm" })}`}
              >
                Notifications
                {unreadNotifications > 0 && (
                  <Badge className="ml-1.5 border-transparent bg-primary px-1.5 text-primary-foreground">
                    {unreadNotifications}
                  </Badge>
                )}
              </Link>
              <Link
                href="/dashboard"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Dashboard
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
