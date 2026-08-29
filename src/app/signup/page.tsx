import Link from "next/link";
import { signup } from "@/app/auth/actions";
import { Button, buttonVariants } from "@/components/ui/button";
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

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; check?: string }>;
}) {
  const { error, check } = await searchParams;

  if (check === "email") {
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
        <Card>
          <CardHeader>
            <CardTitle>Check your email</CardTitle>
            <CardDescription>
              We&apos;ve sent you a confirmation link. Click it to finish creating
              your account, then complete your profile.
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Link href="/login" className={buttonVariants({ variant: "outline" })}>
              Back to log in
            </Link>
          </CardFooter>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>
            Tip: sign up with your university or health-service email to get verified instantly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}
          <form action={signup} className="flex flex-col gap-4">
            <div className="grid gap-2">
              <Label htmlFor="fullName">Full name</Label>
              <Input id="fullName" name="fullName" required autoComplete="name" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" name="email" required autoComplete="email" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <label className="flex items-start gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                name="confirmAge"
                required
                className="mt-0.5 size-4 shrink-0 rounded border-input accent-primary"
              />
              <span>I am 18 or over.</span>
            </label>
            <label className="flex items-start gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                name="acceptTerms"
                required
                className="mt-0.5 size-4 shrink-0 rounded border-input accent-primary"
              />
              <span>
                I accept the{" "}
                <Link href="/terms" className="underline" target="_blank">
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link href="/privacy" className="underline" target="_blank">
                  Privacy Notice
                </Link>
                , and I will not upload patient-identifiable, confidential
                clinical or other confidential NHS/university information.
              </span>
            </label>
            <Button type="submit" className="mt-2 w-full">
              Create account
            </Button>
          </form>
        </CardContent>
        <CardFooter className="text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="ml-1 font-medium text-primary underline">
            Log in
          </Link>
        </CardFooter>
      </Card>
    </main>
  );
}
