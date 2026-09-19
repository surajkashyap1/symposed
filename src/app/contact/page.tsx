import type { Metadata } from "next";
import { getSessionUser } from "@/lib/auth";
import { submitContactMessage } from "@/app/contact/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Contact us | Symposed",
  description:
    "Send Symposed feedback, complaints, safety reports or data protection requests.",
};

const TOPIC_OPTIONS = [
  { value: "feedback", label: "Feedback or improvement idea" },
  { value: "complaint", label: "Complaint" },
  { value: "abuse or safety", label: "Abuse or safety concern" },
  { value: "data protection", label: "Data protection request or complaint" },
  { value: "other", label: "Something else" },
];

export default async function ContactPage({
  searchParams,
}: {
  searchParams: Promise<{ sent?: string; error?: string }>;
}) {
  const { sent, error } = await searchParams;
  const user = await getSessionUser();

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Contact us</CardTitle>
          <CardDescription>
            Feedback, improvement ideas, complaints, safety concerns or data
            protection requests, we read everything. Please don&apos;t include
            patient or confidential information.
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
              Thanks, your message has been received. If it needs a reply
              we&apos;ll come back to you at the email you gave. Data protection
              complaints are acknowledged within 30 days.
            </p>
          ) : (
            <form action={submitContactMessage} className="flex flex-col gap-4">
              <div className="grid gap-2">
                <Label htmlFor="topic">Topic</Label>
                <Select id="topic" name="topic" defaultValue="feedback" options={TOPIC_OPTIONS} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="email">Your email {user ? "" : "(so we can reply)"}</Label>
                <Input
                  id="email"
                  type="email"
                  name="email"
                  defaultValue={user?.email ?? ""}
                  placeholder="you@example.com"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="message">Message</Label>
                <Textarea
                  id="message"
                  name="message"
                  rows={6}
                  required
                  maxLength={5000}
                  placeholder="What would you like to tell us?"
                />
              </div>
              <Button type="submit" className="mt-2 w-full">
                Send message
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
