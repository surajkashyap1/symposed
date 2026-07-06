import Link from "next/link";
import { getSessionUser } from "@/lib/auth";
import { updatePassword } from "@/app/auth/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Reached from the emailed recovery link, which establishes a session via
// /auth/confirm before landing here.
export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const user = await getSessionUser();

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Choose a new password</CardTitle>
          <CardDescription>
            {user
              ? `Setting a new password for ${user.email}.`
              : "This reset link is invalid or has expired."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          {user ? (
            <form action={updatePassword} className="flex flex-col gap-4">
              <div className="grid gap-2">
                <Label htmlFor="password">New password</Label>
                <Input
                  id="password"
                  type="password"
                  name="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="confirm">Confirm new password</Label>
                <Input
                  id="confirm"
                  type="password"
                  name="confirm"
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
              <Button type="submit" className="mt-2 w-full">
                Update password
              </Button>
            </form>
          ) : (
            <Link
              href="/forgot-password"
              className="text-sm font-medium text-primary underline"
            >
              Request a new reset link
            </Link>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
