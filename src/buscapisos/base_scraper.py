"""Contrato común y factoría de scrapers (BaseScraper + ScraperFactory).

El orquestador usa ``ScraperFactory.create(url)`` para instanciar el extractor
adecuado leyendo únicamente el dominio de la URL. Cada nueva fuente se registra
como una "pieza Lego" independiente sin tocar la lógica del orquestador.
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol
from urllib.parse import urlparse

from playwright.async_api import Page

from buscapisos.models import Listing


class UnknownSourceError(Exception):
    """Se lanza cuando no hay ningún scraper registrado para el dominio de la URL."""


class BaseScraper(Protocol):
    """Contrato que toda pieza de extracción debe implementar.

    Metadatos de clase (obligatorios por convención):
      * source      -> valor canónico compatible con la DB
                       ("inmovilla" | "idealista" | "boe" | "other")
      * source_name -> identificador legible de la fuente ("finn.no", "kyero", ...)
      * domains     -> dominios que gestiona ("inmovilla.com", ...)

    Métodos de instancia (obligatorios):
      * parse(content, url)  -> extracción pura (testeable sin I/O)
      * scrape(page, url)    -> navegación + parse (async)
    """

    source: ClassVar[str]
    source_name: ClassVar[str]
    domains: ClassVar[tuple[str, ...]]

    def parse(self, content: Any, url: str) -> Listing:
        """Extrae un Listing a partir del contenido crudo (HTML o JSON)."""
        ...

    async def scrape(self, page: Page, url: str) -> Listing:
        """Navega (si aplica) y delega en parse()."""
        ...


def extract_domain(url: str) -> str:
    """Devuelve el dominio normalizado de una URL (sin ``www.``, en minúsculas)."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class ScraperFactory:
    """Instancia el extractor adecuado leyendo el dominio de la URL."""

    _registry: list[type[BaseScraper]] = []

    @classmethod
    def register(cls, scraper_cls: type[BaseScraper]) -> type[BaseScraper]:
        """Registra un scraper y lo devuelve para poder usarse como decorador."""
        cls._registry.append(scraper_cls)
        return scraper_cls

    @classmethod
    def create(cls, url: str) -> BaseScraper:
        """Devuelve una instancia del scraper cuyo dominio coincide con la URL."""
        domain = extract_domain(url)
        for scraper_cls in cls._registry:
            for registered in scraper_cls.domains:
                # Coincidencia exacta o subdominio (demo.inmovilla.com -> inmovilla.com).
                if domain == registered or domain.endswith("." + registered):
                    return scraper_cls()
        raise UnknownSourceError(
            f"No hay scraper registrado para el dominio {domain!r}"
        )

    @classmethod
    def clear(cls) -> None:
        """Vacía el registro (útil en tests)."""
        cls._registry.clear()
