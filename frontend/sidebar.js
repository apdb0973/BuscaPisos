/**
 * Lógica del Sidebar de Inteligencia (Phase 4.2)
 * Patrón IIFE para encapsular la lógica.
 */
(function() {
    const sidebar = document.getElementById('sidebar');
    const content = document.getElementById('sidebar-content');
    const closeBtn = document.getElementById('sidebar-close');

    const ITP_GENERAL = 0.065;
    const ITP_AUCTION = 0.07;

    function escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function getConfig() {
        const env = window.ENV || {};
        return {
            url: env.SUPABASE_URL || '',
            key: env.SUPABASE_ANON_KEY || '',
        };
    }

    function itpRate(source) {
        if (source === 'boe') return ITP_AUCTION;
        return ITP_GENERAL;
    }

    function openSidebar(propertyId) {
        if (!sidebar || !content) return;
        sidebar.classList.remove('translate-x-full');
        sidebar.classList.add('translate-x-0');
        content.innerHTML = '<p class="text-gray-500">Cargando…</p>';

        fetchProperty(propertyId)
            .then(renderProperty)
            .catch(function (err) {
                content.innerHTML = '<p class="text-red-500">Error: ' + escapeHtml(err.message) + '</p>';
            });
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('translate-x-0');
        sidebar.classList.add('translate-x-full');
    }

    async function fetchProperty(propertyId) {
        const cfg = getConfig();
        if (!cfg.url || !cfg.key) throw new Error('Supabase no configurado');

        const select = 'id,title,area,bedrooms,property_type,listings(source,price,url,price_history(price,observed_at))';
        const url = cfg.url + '/rest/v1/properties?select=' + select + '&id=eq.' + propertyId;

        const response = await fetch(url, {
            headers: {
                'apikey': cfg.key,
                'Authorization': 'Bearer ' + cfg.key,
                'Accept': 'application/json',
            },
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);

        const rows = await response.json();
        if (!rows || !rows.length) throw new Error('Propiedad no encontrada');
        return rows[0];
    }

    function currentPrice(listing) {
        const history = listing.price_history || [];
        if (history.length) return history[history.length - 1].price;
        return listing.price;
    }

    function renderProperty(p) {
        const listings = p.listings || [];

        const listingsHtml = listings.map(function (l) {
            return (
                '<li class="border-b border-gray-200 py-2">' +
                '<div class="font-semibold text-gray-800">' + escapeHtml(l.source) + '</div>' +
                '<div class="text-sm text-gray-600">Precio: ' + escapeHtml(currentPrice(l)) + ' €</div>' +
                '<div class="text-sm text-gray-500 truncate">' + escapeHtml(l.url || '') + '</div>' +
                '</li>'
            );
        }).join('');

        // Historial de precios consolidado de todos los anuncios.
        const entries = [];
        listings.forEach(function (l) {
            (l.price_history || []).forEach(function (h) {
                entries.push({ price: h.price, observed_at: h.observed_at });
            });
        });
        entries.sort(function (a, b) {
            return new Date(a.observed_at) - new Date(b.observed_at);
        });
        const historyHtml = entries.map(function (h) {
            return (
                '<li class="text-sm text-gray-600 py-1">' +
                escapeHtml(h.price) + ' € — ' + escapeHtml(h.observed_at) +
                '</li>'
            );
        }).join('');

        // Fiscalidad canaria sobre el precio más bajo.
        let refPrice = null;
        let refSource = null;
        listings.forEach(function (l) {
            const price = parseFloat(currentPrice(l));
            if (!isNaN(price) && (refPrice === null || price < refPrice)) {
                refPrice = price;
                refSource = l.source;
            }
        });

        let fiscalHtml = '<p class="text-sm text-gray-500">Sin anuncios</p>';
        if (refPrice !== null) {
            const rate = itpRate(refSource);
            const itp = refPrice * rate;
            const total = refPrice + itp;
            fiscalHtml =
                '<div class="text-sm text-gray-700 space-y-1">' +
                '<p>Precio de referencia: ' + refPrice.toLocaleString('es-ES') + ' €</p>' +
                '<p>ITP (' + (rate * 100) + ' %): ' + itp.toLocaleString('es-ES') + ' €</p>' +
                '<p class="font-semibold">Coste total estimado: ' + total.toLocaleString('es-ES') + ' €</p>' +
                '</div>';
        }

        content.innerHTML =
            '<h2 class="property-title text-xl font-bold text-gray-800 mb-2">' + escapeHtml(p.title) + '</h2>' +
            '<p class="text-sm text-gray-600">Tipo: ' + escapeHtml(p.property_type || 'N/A') + '</p>' +
            '<p class="text-sm text-gray-600">Área: ' + (p.area ? escapeHtml(p.area) + ' m²' : 'N/A') + '</p>' +
            '<p class="text-sm text-gray-600">Habitaciones: ' + (p.bedrooms != null ? escapeHtml(p.bedrooms) : 'N/A') + '</p>' +
            '<h3 class="font-semibold text-gray-800 mt-4 mb-2">Anuncios vinculados</h3>' +
            '<ul>' + (listingsHtml || '<li class="text-sm text-gray-500">Sin anuncios</li>') + '</ul>' +
            '<h3 class="font-semibold text-gray-800 mt-4 mb-2">Historial de precios</h3>' +
            '<ul>' + (historyHtml || '<li class="text-sm text-gray-500">Sin historial</li>') + '</ul>' +
            '<h3 class="font-semibold text-gray-800 mt-4 mb-2">Fiscalidad canaria</h3>' +
            fiscalHtml;
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeSidebar);
    }

    window.openSidebar = openSidebar;
    window.closeSidebar = closeSidebar;
})();
