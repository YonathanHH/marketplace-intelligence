"""Build the Indonesia province map asset used by the Coverage view.

Source: Natural Earth 1:50m Admin-1 states/provinces (public domain).
        https://github.com/nvkelso/natural-earth-vector

The raw file covers the whole world at ~2.3 MB. This script isolates Indonesia,
simplifies the geometry, projects it to SVG coordinates and writes a compact
asset the frontend can import directly - so the app renders the map offline
with no mapping library and no runtime tile/GeoJSON fetch.

Steps:
  1. Filter to Indonesia only (the platform operates in one country).
  2. Drop islands below an area threshold - Indonesia has ~17,000 of them and
     the sub-pixel ones cost bytes without changing what the map communicates.
  3. Ramer-Douglas-Peucker simplification, then coordinate rounding.
  4. Mercator-project to a fixed viewBox and emit SVG path strings.

Usage:
    python scripts/build_geo.py [--out web/src/data/indonesia.json]

The output is committed, so this only needs re-running to change the source or
the simplification settings.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_1_states_provinces.geojson"
)

# Natural Earth's names -> the province names used in the dataset.
NAME_OVERRIDES = {
    "Jakarta Raya": "DKI Jakarta",
    "Yogyakarta": "DI Yogyakarta",
}

# Rendering target. Indonesia is ~5x wider than tall, so a wide canvas keeps
# the shape natural without letterboxing.
VIEW_WIDTH = 1000.0
PADDING = 8.0

# Tuning: keep the archipelago readable, drop what a reader cannot see.
MIN_RING_AREA = 0.02   # square degrees (~a 15 km island at this latitude)
SIMPLIFY_EPSILON = 0.012  # degrees (~1.3 km)
COORD_DECIMALS = 2     # after projection, in SVG units


def fetch_source(cache: Path) -> dict:
    if cache.exists():
        print(f"Using cached source: {cache}")
        return json.loads(cache.read_text(encoding="utf-8"))
    print(f"Downloading {SOURCE_URL} ...")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        payload = response.read().decode("utf-8")
    cache.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def ring_area(ring: list[list[float]]) -> float:
    """Shoelace area in square degrees (sign ignored)."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def simplify(points: list[list[float]], epsilon: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker, iterative to avoid deep recursion on long rings."""
    if len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        x1, y1 = points[start]
        x2, y2 = points[end]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)

        worst_index, worst_dist = -1, 0.0
        for i in range(start + 1, end):
            px, py = points[i]
            if norm == 0:
                dist = math.hypot(px - x1, py - y1)
            else:
                dist = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
            if dist > worst_dist:
                worst_index, worst_dist = i, dist

        if worst_index != -1 and worst_dist > epsilon:
            keep[worst_index] = True
            stack.append((start, worst_index))
            stack.append((worst_index, end))

    return [p for p, k in zip(points, keep) if k]


def polygons_of(geometry: dict) -> list[list[list[float]]]:
    """Flatten Polygon/MultiPolygon into a list of outer rings."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Polygon":
        return [coords[0]]
    if kind == "MultiPolygon":
        return [polygon[0] for polygon in coords]
    raise ValueError(f"Unsupported geometry: {kind}")


def mercator_y(lat: float) -> float:
    lat = max(-85.0, min(85.0, lat))
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="web/src/data/indonesia.json")
    parser.add_argument("--cache", default=".tmpgeo/ne50.geojson")
    args = parser.parse_args()

    source = fetch_source(Path(args.cache))
    features = [
        f for f in source["features"]
        if f["properties"].get("admin") == "Indonesia"
    ]
    if not features:
        raise SystemExit("No Indonesian features found in the source file.")
    print(f"Indonesia features: {len(features)}")

    # --- collect + simplify rings -----------------------------------------
    provinces: list[dict] = []
    dropped = 0
    for feature in features:
        name = feature["properties"]["name"]
        name = NAME_OVERRIDES.get(name, name)

        rings: list[list[list[float]]] = []
        for ring in polygons_of(feature["geometry"]):
            if ring_area(ring) < MIN_RING_AREA:
                dropped += 1
                continue
            simplified = simplify(ring, SIMPLIFY_EPSILON)
            if len(simplified) >= 4:
                rings.append(simplified)

        if not rings:  # a province made entirely of small islands - keep its largest
            largest = max(polygons_of(feature["geometry"]), key=ring_area)
            rings = [simplify(largest, SIMPLIFY_EPSILON / 3)]

        provinces.append({
            "name": name,
            "rings": rings,
            "lat": float(feature["properties"].get("latitude") or 0.0),
            "lon": float(feature["properties"].get("longitude") or 0.0),
        })
    print(f"Dropped {dropped} sub-threshold islands")

    # --- fit a Mercator projection to the retained geometry ----------------
    xs = [pt[0] for p in provinces for ring in p["rings"] for pt in ring]
    ys = [mercator_y(pt[1]) for p in provinces for ring in p["rings"] for pt in ring]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)

    scale = (VIEW_WIDTH - 2 * PADDING) / (max_x - min_x)
    view_height = (max_y - min_y) * scale + 2 * PADDING

    def project(lon: float, lat: float) -> tuple[float, float]:
        x = (lon - min_x) * scale + PADDING
        y = (max_y - mercator_y(lat)) * scale + PADDING
        return round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)

    output = []
    for province in provinces:
        parts = []
        for ring in province["rings"]:
            points = [project(lon, lat) for lon, lat in ring]
            head = points[0]
            body = "L".join(f"{x} {y}" for x, y in points[1:])
            parts.append(f"M{head[0]} {head[1]}L{body}Z")
        label_x, label_y = project(province["lon"], province["lat"])
        output.append({
            "name": province["name"],
            "d": "".join(parts),
            "cx": label_x,
            "cy": label_y,
        })

    output.sort(key=lambda p: p["name"])
    asset = {
        "source": "Natural Earth 1:50m Admin-1 (public domain)",
        "projection": "Mercator, fitted to Indonesia",
        "viewBox": f"0 0 {round(VIEW_WIDTH)} {round(view_height)}",
        "provinces": output,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asset, separators=(",", ":")), encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    points = sum(p["d"].count("L") + p["d"].count("M") for p in output)
    print(f"\nWrote {out_path} - {len(output)} provinces, ~{points:,} points, {size_kb:.0f} KB")
    print(f"viewBox: {asset['viewBox']}")


if __name__ == "__main__":
    main()
