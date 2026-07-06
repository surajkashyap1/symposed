-- Manual migration: add messaging tables to the Supabase Realtime publication
-- so the browser receives live INSERTs (live chat + notifications).
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0002_realtime_messaging.sql
-- Re-run safely on a fresh database.
--
-- NOTE: RLS is now enabled everywhere with no policies (0004_enable_rls.sql),
-- so Realtime broadcasts nothing to browser subscribers. If live chat or
-- notification streaming returns, add per-table select policies so users
-- only receive their own rows.

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'messages'
  ) then
    alter publication supabase_realtime add table public.messages;
  end if;

  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'notifications'
  ) then
    alter publication supabase_realtime add table public.notifications;
  end if;
end $$;
