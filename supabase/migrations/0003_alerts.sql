-- =============================================================================
-- 0003_alerts.sql
-- Tabla de estado de alertas para no reenviar notificaciones duplicadas.
--
-- Cada alerta detectada se inserta una sola vez (dedup_key UNIQUE). La columna
-- notified_at marca cuándo se envió a Telegram; el pipeline solo reenvía
-- alertas nuevas (las que se insertan por primera vez).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.alerts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dedup_key   text NOT NULL UNIQUE,
    type        text NOT NULL CHECK (type IN ('CAPITULATION', 'ARBITRAGE')),
    property_id uuid REFERENCES public.properties(id) ON DELETE CASCADE,
    message     text NOT NULL,
    first_seen  timestamptz NOT NULL DEFAULT now(),
    notified_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_alerts_unnotified
    ON public.alerts (notified_at)
    WHERE notified_at IS NULL;

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.alerts
    TO authenticated, service_role;

CREATE POLICY "authenticated_all_alerts" ON public.alerts
    FOR ALL TO authenticated, service_role
    USING (true) WITH CHECK (true);
