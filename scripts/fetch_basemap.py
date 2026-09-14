#!/usr/bin/env python3
"""Cache Esri World Imagery 2D basemap for the Egypt watch bbox."""
import io
import math
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"}
TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
BBOX = [25.0, 22.0, 35.0, 32.0]
ZOOM = 7


def deg2num(lat, lon, z):
    n = 2.0 ** z
    xt = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    yt = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return xt, yt


def main():
    lon_min, lat_min, lon_max, lat_max = BBOX
    x0, y_top = deg2num(lat_max, lon_min, ZOOM)
    x1, y_bot = deg2num(lat_min, lon_max, ZOOM)
    nx, ny = x1 - x0 + 1, y_bot - y_top + 1
    print(f"zoom {ZOOM}: {nx}x{ny} = {nx * ny} tiles")
    canvas = Image.new("RGB", (nx * 256, ny * 256), (13, 32, 54))
    for ix in range(nx):
        for iy in range(ny):
            url = TILE.format(z=ZOOM, x=x0 + ix, y=y_top + iy)
            for _ in range(3):
                try:
                    r = requests.get(url, headers=UA, timeout=40)
                    r.raise_for_status()
                    canvas.paste(Image.open(io.BytesIO(r.content)).convert("RGB"), (ix * 256, iy * 256))
                    break
                except Exception as e:
                    print(f"tile retry: {e}")
                    time.sleep(2)
            time.sleep(0.3)
    out = ROOT / "data" / "basemap_sat.png"
    canvas.save(out)
    # georeference sidecar
    def num2deg(xt, yt):
        n = 2.0 ** ZOOM
        lon = xt / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))
        return lon, lat
    wlon, _ = num2deg(x0, y_top)
    elon, _ = num2deg(x1 + 1, y_top)
    _, nlat = num2deg(x0, y_top)
    _, slat = num2deg(x0, y_bot + 1)
    (ROOT / "data" / "basemap_sat.json").write_text(
        __import__("json").dumps({"wlon": wlon, "elon": elon, "nlat": nlat, "slat": slat,
                                  "w": canvas.width, "h": canvas.height}))
    print(f"basemap -> {out} ({canvas.width}x{canvas.height})")


if __name__ == "__main__":
    main()
