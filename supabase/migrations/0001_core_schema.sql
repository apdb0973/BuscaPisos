-- =============================================================================
-- 0001_core_schema.sql
-- Core relational schema for the Gran Canaria real-estate aggregator.
--
-- Creates:
--   * Extensions (PostGIS for Catastro X,Y coordinates, pgcrypto for UUIDs)
--   * properties    -- the unique, deduplicated physical property
--   * listings      -- raw scraped ads (Inmovilla, Idealista, BOE, ...)
--   * price_history -- price-variation tracking (1:N with listings)
--   * PL/pgSQL functions + triggers for automatic last_seen maintenance
--   * Row Level Security (RLS) policies + grants
--
-- Design notes:
--   * last_seen uses clock_timestamp() (not now()) so every scraper detection
--     gets a fresh timestamp even within a single transaction. now() is
--     transaction-stable and would NOT advance inside one transaction, which
--     is exactly what the pgTAP trigger test depends on.
--   * Grants follow Supabase's model: table privileges are broad, RLS does the
--     real gating. anon has table privileges but only SELECT policies (and no
--     INSERT/UPDATE/DELETE policies), so its writes are rejected by RLS.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Roles (Supabase already provides anon / authenticated / service_role; these
-- guarded blocks only make the migration runnable on a bare Postgres for pgTAP).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- properties: the unique physical property (deduplicated entity)
-- ---------------------------------------------------------------------------
CREATE TABLE public.properties (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    last_seen            timestamptz,
    property_type        text NOT NULL
                         CHECK (property_type IN
                            ('house','apartment','commercial','land','garage','other')),
    title                text,
    location             geometry(Point, 4326),   -- Catastro X,Y (EPSG:4326)
    address              text,
    city                 text,
    province             text,
    postal_code          text,
    cru                  text UNIQUE,              -- Código Registral Único
    referencia_catastral text UNIQUE,              -- Referencia Catastral
    area                 numeric(10,2),            -- built m2
    bedrooms             integer,
    bathrooms            integer,
    is_public            boolean NOT NULL DEFAULT false
);

CREATE INDEX idx_properties_location_gist ON public.properties USING GIST (location);

-- ---------------------------------------------------------------------------
-- listings: raw scraped ads (Inmovilla, Idealista, BOE, ...)
-- ---------------------------------------------------------------------------
CREATE TABLE public.listings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id   uuid NOT NULL REFERENCES public.properties(id) ON DELETE RESTRICT,
    source        text NOT NULL
                  CHECK (source IN ('inmovilla','idealista','boe','other')),
    source_id     text NOT NULL,
    url           text,
    title         text,
    description   text,
    price         numeric(12,2),
    currency      char(3) NOT NULL DEFAULT 'EUR',
    area          numeric(10,2),
    bedrooms      integer,
    bathrooms     integer,
    status        text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','inactive','sold','rented','removed')),
    location      geometry(Point, 4326),           -- optional source coordinates
    first_seen    timestamptz NOT NULL DEFAULT now(),
    last_seen     timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT listings_source_source_id_key UNIQUE (source, source_id)
);

CREATE INDEX idx_listings_property_id    ON public.listings (property_id);
CREATE INDEX idx_listings_location_gist  ON public.listings USING GIST (location);
CREATE INDEX idx_listings_source         ON public.listings (source);

-- ---------------------------------------------------------------------------
-- price_history: price variations per listing (1:N with listings)
-- ---------------------------------------------------------------------------
CREATE TABLE public.price_history (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id  uuid NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
    price       numeric(12,2) NOT NULL,
    currency    char(3) NOT NULL DEFAULT 'EUR',
    observed_at timestamptz NOT NULL DEFAULT now(),
    source      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_price_history_listing_id
    ON public.price_history (listing_id, observed_at DESC);

-- =============================================================================
-- Triggers: automatic last_seen maintenance
-- =============================================================================

-- (1) Every INSERT/UPDATE on a listing marks it as "just seen" by the scraper.
CREATE OR REPLACE FUNCTION public.fn_listings_set_last_seen()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.last_seen := clock_timestamp();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_listings_set_last_seen ON public.listings;
CREATE TRIGGER trg_listings_set_last_seen
BEFORE INSERT OR UPDATE ON public.listings
FOR EACH ROW EXECUTE FUNCTION public.fn_listings_set_last_seen();

-- (2) Keep the parent property's last_seen in sync with its listings.
CREATE OR REPLACE FUNCTION public.fn_sync_property_last_seen()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.properties
       SET last_seen = NEW.last_seen
     WHERE id = NEW.property_id;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_property_last_seen ON public.listings;
CREATE TRIGGER trg_sync_property_last_seen
AFTER INSERT OR UPDATE ON public.listings
FOR EACH ROW EXECUTE FUNCTION public.fn_sync_property_last_seen();

-- (3) A new price observation also refreshes the listing (and, in turn, the
--     property via the triggers above).
CREATE OR REPLACE FUNCTION public.fn_sync_last_seen_from_price()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.listings
       SET last_seen = clock_timestamp()
     WHERE id = NEW.listing_id;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_last_seen_from_price ON public.price_history;
CREATE TRIGGER trg_sync_last_seen_from_price
AFTER INSERT ON public.price_history
FOR EACH ROW EXECUTE FUNCTION public.fn_sync_last_seen_from_price();

-- (4) Keep updated_at fresh on properties and listings.
CREATE OR REPLACE FUNCTION public.fn_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_properties_touch_updated_at ON public.properties;
CREATE TRIGGER trg_properties_touch_updated_at
BEFORE UPDATE ON public.properties
FOR EACH ROW EXECUTE FUNCTION public.fn_touch_updated_at();

DROP TRIGGER IF EXISTS trg_listings_touch_updated_at ON public.listings;
CREATE TRIGGER trg_listings_touch_updated_at
BEFORE UPDATE ON public.listings
FOR EACH ROW EXECUTE FUNCTION public.fn_touch_updated_at();

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE public.properties    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_history ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.properties, public.listings, public.price_history
    TO anon, authenticated, service_role;

-- anon: read-only access to public data (no INSERT/UPDATE/DELETE policies).
CREATE POLICY "anon_select_public_properties" ON public.properties
    FOR SELECT TO anon
    USING (is_public = true);

CREATE POLICY "anon_select_public_listings" ON public.listings
    FOR SELECT TO anon
    USING (
        EXISTS (
            SELECT 1
              FROM public.properties p
             WHERE p.id = property_id
               AND p.is_public = true
        )
    );

CREATE POLICY "anon_select_public_price_history" ON public.price_history
    FOR SELECT TO anon
    USING (
        EXISTS (
            SELECT 1
              FROM public.listings l
              JOIN public.properties p ON p.id = l.property_id
             WHERE l.id = listing_id
               AND p.is_public = true
        )
    );

-- authenticated / service_role: full access (the scraper runs as service_role,
-- which also bypasses RLS via BYPASSRLS).
CREATE POLICY "authenticated_all_properties" ON public.properties
    FOR ALL TO authenticated, service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "authenticated_all_listings" ON public.listings
    FOR ALL TO authenticated, service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "authenticated_all_price_history" ON public.price_history
    FOR ALL TO authenticated, service_role
    USING (true) WITH CHECK (true);
