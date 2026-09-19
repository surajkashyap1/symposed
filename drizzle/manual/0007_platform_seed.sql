-- Platform config single row (amendment §8): application credit tiers (§8.9),
-- bounded direct-support allowance (§8.8) and the optional 14-day vesting flag
-- (§8.7, off at launch). All administrator-editable on /admin.
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0007_platform_seed.sql
-- Safe to re-run.

insert into platform_config
  (id, credits_standard, credits_lister, credits_guide_lister,
   support_allowance, support_response_days, vest_listing_days)
values (1, 3, 6, 9, 3, 7, 0)
on conflict (id) do nothing;
