-- Guide pricing config (single row, admin-editable) and the PRIVATE storage
-- bucket for delivered guide files.
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0006_guides_seed.sql
-- Safe to re-run.

-- Amendment §2 price ladder: the first 25 guides are FREE, the next 25 are
-- the £25 tier, then £45. `payments_enabled` is false at launch, so the
-- checkout step is skipped and requests go straight to the queue at no charge
-- while the full Stripe path stays built and ready. All values are
-- admin-editable on /admin/guides (nothing hardcoded).
insert into guide_pricing_config
  (id, standard_price_pence, intro_price_pence, intro_quantity, free_quantity, payments_enabled, blocked_countries)
values (1, 4500, 2500, 25, 25, false, array['IN', 'PK'])
on conflict (id) do nothing;

-- Existing environments (row already present) keep their configured values;
-- adjust the ladder and flip payments on from /admin/guides. To migrate an
-- existing row to the amendment defaults, run once:
--   update guide_pricing_config
--     set standard_price_pence = 4500, intro_price_pence = 2500,
--         intro_quantity = 25, free_quantity = 25, payments_enabled = false
--   where id = 1;

-- No public policies: only the service role reads/writes. Files are served
-- through an authenticated app route tied to the buyer's account.
insert into storage.buckets (id, name, public)
values ('guide-files', 'guide-files', false)
on conflict (id) do update set public = false;
