/**
 * Lógica del Mapa Cartográfico (Phase 4.2)
 * Patrón IIFE para encapsular la lógica.
 */
(function() {
    let mapInstance = null;

    function initMap() {
        mapInstance = L.map('map').setView([28.1174, -15.4411], 12);

        // 1. Capa Base: OpenStreetMap
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap'
        }).addTo(mapInstance);

        // 2. Capa WMS: GRAFCAN Planeamiento
        L.tileLayer.wms('https://idecan2.grafcan.es/ServicioWMS/Planeamiento', {
            layers: 'Planeamiento',
            format: 'image/png',
            transparent: true,
            opacity: 0.4,
            attribution: '© GRAFCAN'
        }).addTo(mapInstance);
    }

    function addMarker(lat, lng, title, propertyId) {
        if (!mapInstance) return;
        const marker = L.marker([lat, lng]).addTo(mapInstance);
        if (propertyId != null) {
            marker.on('click', function () {
                if (typeof window.openSidebar === 'function') {
                    window.openSidebar(propertyId);
                }
            });
        } else {
            marker.bindPopup('<b>' + title + '</b>');
        }
        return marker;
    }

    async function loadProperties() {
        const env = window.ENV || {};
        const supabaseUrl = env.SUPABASE_URL || '';
        const supabaseKey = env.SUPABASE_ANON_KEY || '';

        if (!supabaseUrl || !supabaseKey) return;

        try {
            const response = await fetch(`${supabaseUrl}/rest/v1/properties?select=id,title,location&location=not.is.null&limit=100`, {
                headers: {
                    'apikey': supabaseKey,
                    'Authorization': `Bearer ${supabaseKey}`,
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
            const data = await response.json();

            data.forEach(property => {
                if (property.location && property.location.coordinates) {
                    const [lng, lat] = property.location.coordinates;
                    addMarker(lat, lng, property.title || 'Propiedad', property.id);
                }
            });
        } catch (error) {
            console.error('Error cargando propiedades:', error);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        initMap();
        loadProperties();
    });

    window.BuscaPisosMap = {
        get map() { return mapInstance; },
        addMarker,
        loadProperties
    };
})();
