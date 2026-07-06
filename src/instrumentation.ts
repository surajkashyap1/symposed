import type { Instrumentation } from "next";

// Zero-budget error monitoring: unhandled server errors land in the
// app_errors table and surface on /admin. Never throws — a broken error
// logger must not take down the request it was reporting on.
export const onRequestError: Instrumentation.onRequestError = async (
  err,
  request,
  context
) => {
  try {
    const { db } = await import("@/db");
    const { appErrors } = await import("@/db/schema");
    const { lt } = await import("drizzle-orm");

    const message = err instanceof Error ? err.message : String(err);
    const digest =
      typeof err === "object" && err !== null && "digest" in err
        ? String((err as { digest: unknown }).digest)
        : null;
    const stack = err instanceof Error ? err.stack ?? null : null;

    await db.insert(appErrors).values({
      message: message.slice(0, 1000),
      digest,
      stack: stack?.slice(0, 4000) ?? null,
      path: request.path.slice(0, 500),
      method: request.method,
      routePath: context.routePath,
      routeType: context.routeType,
    });

    // Errors are rare enough that pruning inline beats a scheduled job.
    const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    await db.delete(appErrors).where(lt(appErrors.createdAt, cutoff));
  } catch (loggingError) {
    console.error("onRequestError failed to record", loggingError);
  }
};
