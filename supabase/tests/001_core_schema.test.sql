-- =============================================================================
-- 001_core_schema.test.sql
-- pgTAP unit tests for the core schema: properties, listings, price_history.
--
-- Run with:  supabase test db
--            (or standalone:  pg_prove -d <db> supabase/tests/001_core_schema.test.sql)
--
-- Notes:
--   * pgTAP is provided by Supabase's test runner; PostGIS and the schema are
--     created by supabase/migrations/0001_core_schema.sql, which must run first.
--   * These tests exercise (a) table existence, (b) UUID primary keys and data
--     types, (c) foreign-key integrity (no orphan listings), (d) the last_seen
--     triggers, (e) ON DELETE CASCADE, and (f) RLS blocking of anon INSERTs.
-- =============================================================================

BEGIN;

SELECT plan(25);

-- ---------------------------------------------------------------------------
-- 1. The three core tables must exist
-- ---------------------------------------------------------------------------
SELECT has_table('public', 'properties',    'table properties exists');
SELECT has_table('public', 'listings',      'table listings exists');
SELECT has_table('public', 'price_history', 'table price_history exists');

-- ---------------------------------------------------------------------------
-- 2. UUID primary keys
-- ---------------------------------------------------------------------------
SELECT col_is_pk('public', 'properties',     'id', 'properties.id is the primary key');
SELECT col_type_is('public', 'properties',   'id', 'uuid', 'properties.id is uuid');
SELECT col_is_pk('public', 'listings',       'id', 'listings.id is the primary key');
SELECT col_type_is('public', 'listings',     'id', 'uuid', 'listings.id is uuid');
SELECT col_is_pk('public', 'price_history',  'id', 'price_history.id is the primary key');
SELECT col_type_is('public', 'price_history','id', 'uuid', 'price_history.id is uuid');

-- ---------------------------------------------------------------------------
-- 3. Key columns and data types (PostGIS geometry + numeric)
-- ---------------------------------------------------------------------------
SELECT has_column('public', 'listings', 'property_id', 'listings has property_id');

SELECT col_type_is(
    'public', 'properties', 'location',
    'geometry(Point,4326)',
    'properties.location is geometry(Point,4326)'
);

SELECT ok(
    (SELECT data_type = 'numeric'
       FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'price'),
    'listings.price is numeric'
);

SELECT ok(
    (SELECT data_type = 'numeric'
       FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'area'),
    'listings.area is numeric'
);

SELECT ok(
    (SELECT data_type = 'numeric'
       FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'price'),
    'price_history.price is numeric'
);

-- ---------------------------------------------------------------------------
-- 4. Foreign keys: no orphan listings / price rows
-- ---------------------------------------------------------------------------
SELECT fk_ok(
    'public', 'listings', 'property_id',
    'public', 'properties', 'id',
    'listings.property_id -> properties.id'
);

SELECT fk_ok(
    'public', 'price_history', 'listing_id',
    'public', 'listings', 'id',
    'price_history.listing_id -> listings.id'
);

-- Inserting a listing whose property does not exist must fail (SQLSTATE 23503).
SELECT throws_ok(
    $$ INSERT INTO public.listings (property_id, source, source_id)
       VALUES ('00000000-0000-0000-0000-000000000000', 'inmovilla', 'orphan-1') $$,
    '23503',
    'orphan listing is rejected by the foreign key'
);

-- ---------------------------------------------------------------------------
-- 5. Trigger: listings.last_seen (and properties.last_seen) maintained
--    automatically on INSERT and UPDATE.
-- ---------------------------------------------------------------------------
-- Seed one public property and one listing, capturing their ids / last_seen.
CREATE TEMP TABLE _test_property AS
WITH ins AS (
    INSERT INTO public.properties (property_type, location, is_public)
    VALUES ('apartment', ST_SetSRID(ST_MakePoint(-15.42, 28.10), 4326), true)
    RETURNING id
)
SELECT id FROM ins;

CREATE TEMP TABLE _test_listing AS
WITH ins AS (
    INSERT INTO public.listings (property_id, source, source_id, price, area)
    SELECT id, 'inmovilla', 'ext-trigger-1', 250000, 80 FROM _test_property
    RETURNING id, last_seen
)
SELECT id, last_seen FROM ins;

SELECT is(
    (SELECT last_seen IS NOT NULL FROM _test_listing),
    true,
    'listings.last_seen is set automatically on INSERT'
);

-- Let time advance so clock_timestamp() yields a strictly newer value.
SELECT pg_sleep(0.1);

UPDATE public.listings
   SET price = price + 1
 WHERE id = (SELECT id FROM _test_listing);

SELECT isnt(
    (SELECT last_seen FROM public.listings WHERE id = (SELECT id FROM _test_listing)),
    (SELECT last_seen FROM _test_listing),
    'listings.last_seen changes automatically on UPDATE'
);

SELECT is(
    (SELECT last_seen FROM public.properties WHERE id = (SELECT id FROM _test_property)),
    (SELECT last_seen FROM public.listings  WHERE id = (SELECT id FROM _test_listing)),
    'properties.last_seen is synced from its listing'
);

-- ---------------------------------------------------------------------------
-- 6. ON DELETE CASCADE: listings -> price_history
-- ---------------------------------------------------------------------------
INSERT INTO public.price_history (listing_id, price)
VALUES ((SELECT id FROM _test_listing), 250000);

SELECT lives_ok(
    $$ DELETE FROM public.listings WHERE id = (SELECT id FROM _test_listing) $$,
    'deleting a listing succeeds'
);

SELECT is(
    (SELECT count(*) FROM public.price_history WHERE listing_id = (SELECT id FROM _test_listing)),
    0,
    'price_history rows are cascade-deleted with their listing'
);

-- ---------------------------------------------------------------------------
-- 7. RLS: the anon role must NOT be able to INSERT
-- ---------------------------------------------------------------------------
SET LOCAL ROLE anon;

SELECT throws_ok(
    $$ INSERT INTO public.properties (property_type, is_public)
       VALUES ('apartment', true) $$,
    '42501',
    'anon INSERT into properties is blocked by RLS'
);

SELECT throws_ok(
    $$ INSERT INTO public.listings (property_id, source, source_id)
       VALUES ('00000000-0000-0000-0000-000000000000', 'inmovilla', 'anon-1') $$,
    '42501',
    'anon INSERT into listings is blocked by RLS'
);

SELECT throws_ok(
    $$ INSERT INTO public.price_history (listing_id, price)
       VALUES ('00000000-0000-0000-0000-000000000000', 100) $$,
    '42501',
    'anon INSERT into price_history is blocked by RLS'
);

RESET ROLE;

-- ---------------------------------------------------------------------------
SELECT * FROM finish();

ROLLBACK;
