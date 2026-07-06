import Link from "next/link";
import { requestPasswordReset } from "@/app/auth/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ sent?: string; error?: string }>;
}) {
  const { sent, error } = await searchParams;

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Reset your password</CardTitle>
          <CardDescription>
            Enter your account email and we&apos;ll send you a link to set a new
            password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          {sent ? (
            <p className="rounded-md bg-accent px-3 py-2 text-sm">
              If an account exists for that email, a reset link is on its way.
              Check your inbox (and spam folder).
            </p>
          ) : (
            <form action={requestPasswordReset} className="flex flex-col gap-4">
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  name="email"
                  required
                  autoComplete="email"
                />
              </div>
              <Button type="submit" className="mt-2 w-full">
                Send reset link
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="text-sm text-muted-foreground">
          Remembered it?{" "}
          <Link href="/login" className="ml-1 font-medium text-primary underline">
            Back to log in
          </Link>
        </CardFooter>
      </Card>
    </main>
  );
}
