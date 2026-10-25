"""Region outlines used to restrict statistics (and drawn on the maps)."""

from __future__ import annotations

import cartopy.io.shapereader as shpreader
import shapely


def _records(name: str):
    path = shpreader.natural_earth(resolution="10m", category="cultural", name=name)
    return shpreader.Reader(path).records()


def build_region(spec: dict | None, extent) -> tuple[object, str]:
    """Return (geometry, label) for the region spec; the domain box when spec is None.

    Spec keys (combined as a union):
        countries: [Spain, Portugal]           Natural Earth admin-0 names
        admin1: {country: Italy, regions: [Toscana]}   admin-1 'region' or 'name'
        box: [W, E, S, N]
        clip_to_domain: true (default) — drop parts outside the domain (e.g. islands)
        name: label used in titles/CSV
    """
    w, e, s, n = extent
    domain_box = shapely.box(w, s, e, n)
    if not spec:
        return domain_box, "domain"
    parts = []
    countries = spec.get("countries") or []
    if countries:
        wanted = {c.lower() for c in countries}
        parts += [
            r.geometry
            for r in _records("admin_0_countries")
            if str(r.attributes.get("ADMIN", "")).lower() in wanted
            or str(r.attributes.get("NAME", "")).lower() in wanted
        ]
    admin1 = spec.get("admin1")
    if admin1:
        country = str(admin1.get("country", "")).lower()
        names = {x.lower() for x in admin1.get("regions", [])}
        parts += [
            r.geometry
            for r in _records("admin_1_states_provinces")
            if str(r.attributes.get("admin", "")).lower() == country
            and (
                str(r.attributes.get("region", "")).lower() in names
                or str(r.attributes.get("name", "")).lower() in names
            )
        ]
    if spec.get("box"):
        bw, be, bs, bn = spec["box"]
        parts.append(shapely.box(bw, bs, be, bn))
    if not parts:
        raise ValueError(f"Region {spec!r} matched no geometry")
    geom = shapely.union_all(parts)
    if spec.get("clip_to_domain", True):
        geom = geom.intersection(domain_box)
    label = spec.get("name") or ", ".join(
        countries + list(admin1.get("regions", []) if admin1 else [])
    )
    return geom, label or "region"
