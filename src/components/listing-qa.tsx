import { askQuestion, answerQuestion } from "@/app/projects/questions-actions";
import type { ListingQuestion } from "@/lib/queries/questions";
import { QUESTION_WORD_LIMIT } from "@/lib/listing-meta";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { WordLimitedField } from "@/components/word-limited-field";
import { ReportContent } from "@/components/report-content";

export function ListingQA({
  projectId,
  questions,
  isOwner,
  isSignedIn,
  isOpen,
}: {
  projectId: string;
  questions: ListingQuestion[];
  isOwner: boolean;
  isSignedIn: boolean;
  isOpen: boolean;
}) {
  return (
    <section id="qa" className="mt-12 scroll-mt-20">
      <h2 className="text-lg font-semibold tracking-tight">
        Questions {questions.length > 0 && `(${questions.length})`}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Public questions and answers about this listing. Don&apos;t include
        personal, contact or patient information — see our{" "}
        <a href="/acceptable-use" className="underline" target="_blank">
          Acceptable Use Policy
        </a>
        .
      </p>

      {questions.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No questions yet.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-4">
          {questions.map((q) => (
            <li key={q.id} className="rounded-lg border p-4">
              <p className="text-sm font-medium">{q.question}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Asked by {q.askerName ?? "a member"}
              </p>

              {isSignedIn && (
                <div className="mt-2">
                  <ReportContent
                    targetType="question"
                    targetId={q.id}
                    backTo={`/projects/${projectId}`}
                  />
                </div>
              )}

              {q.answer ? (
                <div className="mt-3 border-l-2 border-primary pl-3">
                  <p className="text-sm">{q.answer}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Answered by the lister
                  </p>
                </div>
              ) : isOwner ? (
                <form action={answerQuestion} className="mt-3 flex flex-col gap-2">
                  <input type="hidden" name="id" value={q.id} />
                  <input type="hidden" name="projectId" value={projectId} />
                  <Textarea
                    name="answer"
                    rows={2}
                    required
                    placeholder="Write a public answer…"
                  />
                  <Button type="submit" size="sm" variant="outline" className="self-start">
                    Answer
                  </Button>
                </form>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">
                  Awaiting an answer from the lister.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Ask form */}
      {isOpen && isSignedIn && !isOwner && (
        <form action={askQuestion} className="mt-6 flex flex-col gap-2">
          <input type="hidden" name="projectId" value={projectId} />
          <WordLimitedField
            id="question"
            name="question"
            label="Ask a public question"
            max={QUESTION_WORD_LIMIT}
            multiline
            rows={2}
            required
            placeholder="Ask a public question about this project…"
          />
          <Button type="submit" variant="outline" className="self-start">
            Ask a question
          </Button>
        </form>
      )}
    </section>
  );
}
