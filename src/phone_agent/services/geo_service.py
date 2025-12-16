"""Geographic Service for PLZ-based distance calculation.

Provides:
- PLZ (postal code) to coordinates geocoding
- Distance calculation between two points
- Service area validation
- Worker proximity routing support
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import radians, cos, sin, asin, sqrt
from typing import Any
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)


# Common German PLZ coordinates (cache for frequently used)
# Format: PLZ -> (latitude, longitude)
PLZ_CACHE = {
    # Baden-Württemberg (Handwerk demo area)
    "72379": (48.3500, 8.9667),   # Hechingen
    "72336": (48.2722, 8.7500),   # Balingen
    "72764": (48.4833, 9.2167),   # Reutlingen
    "72072": (48.5200, 8.7700),   # Tübingen
    "72762": (48.4833, 9.2167),   # Reutlingen
    "72458": (48.1667, 8.9167),   # Albstadt
    "70173": (48.7758, 9.1829),   # Stuttgart
    "70174": (48.7823, 9.1767),   # Stuttgart
    "70178": (48.7691, 9.1731),   # Stuttgart
    "70182": (48.7715, 9.1881),   # Stuttgart
    "70190": (48.7846, 9.2032),   # Stuttgart
    "70565": (48.7285, 9.1042),   # Stuttgart-Vaihingen
    "70569": (48.7415, 9.0950),   # Stuttgart-Vaihingen
    # Bayern
    "80331": (48.1351, 11.5820),  # München
    "80333": (48.1449, 11.5685),  # München
    "90402": (49.4521, 11.0767),  # Nürnberg
    # NRW
    "40210": (51.2277, 6.7735),   # Düsseldorf
    "50667": (50.9375, 6.9603),   # Köln
    # Berlin
    "10115": (52.5340, 13.3885),  # Berlin-Mitte
    "10117": (52.5163, 13.3889),  # Berlin-Mitte
    # Hamburg
    "20095": (53.5511, 9.9937),   # Hamburg
}


@dataclass
class GeoLocation:
    """Geographic location with coordinates."""

    latitude: float
    longitude: float
    plz: str | None = None
    city: str | None = None
    street: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "plz": self.plz,
            "city": self.city,
            "street": self.street,
        }


@dataclass
class ServiceAreaResult:
    """Result of service area check."""

    is_within_area: bool
    distance_km: float
    service_radius_km: float
    message: str


class GeoService:
    """Service for geographic calculations.

    Provides PLZ geocoding and distance calculations for:
    - Service area validation (is customer within company radius)
    - Worker proximity routing (find nearest worker)
    - Travel distance estimation

    Usage:
        geo = GeoService()

        # Geocode PLZ
        coords = await geo.geocode_plz("72379")

        # Calculate distance
        distance = geo.calculate_distance_km(48.35, 8.97, 48.27, 8.75)

        # Check service area
        result = await geo.is_in_service_area(
            tenant_lat=48.35, tenant_lon=8.97,
            customer_plz="72336",
            service_radius_km=50
        )
    """

    def __init__(
        self,
        api_base_url: str = "https://openplzapi.org",
        cache_enabled: bool = True,
    ):
        """Initialize geo service.

        Args:
            api_base_url: Base URL for PLZ API
            cache_enabled: Enable coordinate caching
        """
        self.api_base_url = api_base_url
        self.cache_enabled = cache_enabled
        self._coordinate_cache: dict[str, tuple[float, float]] = PLZ_CACHE.copy()

    async def geocode_plz(self, plz: str) -> GeoLocation | None:
        """Get coordinates for a German PLZ.

        Args:
            plz: German postal code (5 digits)

        Returns:
            GeoLocation or None if not found
        """
        # Clean PLZ
        plz = plz.strip()[:5]

        # Check cache first
        if self.cache_enabled and plz in self._coordinate_cache:
            lat, lon = self._coordinate_cache[plz]
            return GeoLocation(latitude=lat, longitude=lon, plz=plz)

        # Query external API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base_url}/de/Localities",
                    params={"postalCode": plz},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                if data and len(data) > 0:
                    locality = data[0]
                    lat = locality.get("latitude")
                    lon = locality.get("longitude")
                    city = locality.get("name")

                    if lat and lon:
                        # Cache result
                        if self.cache_enabled:
                            self._coordinate_cache[plz] = (lat, lon)

                        return GeoLocation(
                            latitude=lat,
                            longitude=lon,
                            plz=plz,
                            city=city,
                        )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to geocode PLZ {plz}: {e}")
        except Exception as e:
            logger.error(f"Error geocoding PLZ {plz}: {e}")

        # Fallback: Try to interpolate from nearby PLZ
        return await self._interpolate_plz(plz)

    async def _interpolate_plz(self, plz: str) -> GeoLocation | None:
        """Try to interpolate coordinates from nearby PLZ.

        Args:
            plz: PLZ to interpolate

        Returns:
            Interpolated GeoLocation or None
        """
        # Find PLZ with same 2-digit prefix
        prefix = plz[:2]
        nearby = [
            (p, coords) for p, coords in self._coordinate_cache.items()
            if p.startswith(prefix)
        ]

        if nearby:
            # Average coordinates of nearby PLZ
            avg_lat = sum(c[0] for _, c in nearby) / len(nearby)
            avg_lon = sum(c[1] for _, c in nearby) / len(nearby)

            logger.info(f"Interpolated PLZ {plz} from {len(nearby)} nearby entries")
            return GeoLocation(latitude=avg_lat, longitude=avg_lon, plz=plz)

        return None

    def calculate_distance_km(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two points in kilometers.

        Uses Haversine formula for great-circle distance.

        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates

        Returns:
            Distance in kilometers
        """
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        # Earth radius = 6371 km
        return 6371 * c

    async def is_in_service_area(
        self,
        tenant_lat: float,
        tenant_lon: float,
        customer_plz: str,
        service_radius_km: float,
    ) -> ServiceAreaResult:
        """Check if customer is within company's service radius.

        Args:
            tenant_lat: Company HQ latitude
            tenant_lon: Company HQ longitude
            customer_plz: Customer's PLZ
            service_radius_km: Company's service radius in km

        Returns:
            ServiceAreaResult with distance and status
        """
        # Geocode customer PLZ
        customer_location = await self.geocode_plz(customer_plz)

        if not customer_location:
            return ServiceAreaResult(
                is_within_area=False,
                distance_km=0.0,
                service_radius_km=service_radius_km,
                message=f"Konnte PLZ {customer_plz} nicht finden",
            )

        # Calculate distance
        distance = self.calculate_distance_km(
            tenant_lat, tenant_lon,
            customer_location.latitude, customer_location.longitude,
        )

        is_within = distance <= service_radius_km

        if is_within:
            message = f"Im Einzugsgebiet ({distance:.1f} km von Zentrale)"
        else:
            over_by = distance - service_radius_km
            message = f"Außerhalb des Einzugsgebiets ({distance:.1f} km, {over_by:.1f} km zu weit)"

        return ServiceAreaResult(
            is_within_area=is_within,
            distance_km=round(distance, 2),
            service_radius_km=service_radius_km,
            message=message,
        )

    async def find_nearest_workers(
        self,
        task_lat: float,
        task_lon: float,
        workers: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find nearest workers to a task location.

        Args:
            task_lat: Task latitude
            task_lon: Task longitude
            workers: List of worker dicts with 'plz' or 'latitude'/'longitude'
            limit: Max workers to return

        Returns:
            List of workers sorted by distance (nearest first)
        """
        workers_with_distance = []

        for worker in workers:
            # Get worker coordinates
            if "latitude" in worker and "longitude" in worker:
                worker_lat = worker["latitude"]
                worker_lon = worker["longitude"]
            elif "plz" in worker:
                location = await self.geocode_plz(worker["plz"])
                if not location:
                    continue
                worker_lat = location.latitude
                worker_lon = location.longitude
            else:
                continue

            # Calculate distance
            distance = self.calculate_distance_km(
                task_lat, task_lon, worker_lat, worker_lon
            )

            workers_with_distance.append({
                **worker,
                "distance_km": round(distance, 2),
            })

        # Sort by distance and limit
        workers_with_distance.sort(key=lambda w: w["distance_km"])
        return workers_with_distance[:limit]

    async def geocode_address(
        self,
        street: str,
        plz: str,
        city: str,
    ) -> GeoLocation | None:
        """Geocode a full address.

        Falls back to PLZ geocoding if full address fails.

        Args:
            street: Street address
            plz: Postal code
            city: City name

        Returns:
            GeoLocation or None
        """
        # For now, just use PLZ geocoding
        # TODO: Integrate Nominatim or Google Geocoding for precise addresses
        location = await self.geocode_plz(plz)

        if location:
            location.street = street
            location.city = city

        return location

    def get_cached_plz_count(self) -> int:
        """Get number of PLZ entries in cache.

        Returns:
            Cache size
        """
        return len(self._coordinate_cache)

    def clear_cache(self) -> None:
        """Clear coordinate cache (keeps default entries)."""
        self._coordinate_cache = PLZ_CACHE.copy()
