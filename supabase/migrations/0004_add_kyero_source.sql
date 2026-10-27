-- =============================================================================
-- 0004_add_kyero_source.sql
-- Amplía el CHECK de listings.source para admitir el nuevo conector "kyero".
-- =============================================================================

ALTER TABLE public.listings DROP CONSTRAINT IF EXISTS listings_source_check;

ALTER TABLE public.listings ADD CONSTRAINT listings_source_check
    CHECK (source IN ('inmovilla','idealista','kyero','boe','other'));
