-- =============================================================================
-- 0002_update_location_rpc.sql
-- RPC para actualizar la geometría `location` de una propiedad (PostGIS).
--
-- Lo usa EnrichmentService.geolocate_property: el cliente Supabase no puede
-- inyectar ST_MakePoint/ST_SetSRID en un payload UPDATE, así que lo
-- encapsulamos en una función invocable vía PostgREST (client.rpc).
-- =============================================================================

CREATE OR REPLACE FUNCTION public.update_property_location(
    p_id uuid,
    x double precision,
    y double precision
)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE public.properties
       SET location = ST_SetSRID(ST_MakePoint(x, y), 4326)
     WHERE id = p_id;
$$;

-- Seguridad: solo el rol maestro del backend (service_role) puede ejecutarla.
REVOKE ALL ON FUNCTION public.update_property_location(uuid, double precision, double precision)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_property_location(uuid, double precision, double precision)
    TO service_role;
