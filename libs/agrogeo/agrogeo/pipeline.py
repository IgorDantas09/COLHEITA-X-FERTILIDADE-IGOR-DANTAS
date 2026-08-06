from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gc
import json
import math

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from scipy.optimize import curve_fit
from scipy.spatial import cKDTree, distance
from shapely import contains_xy, points
from shapely.geometry import mapping
from shapely.ops import unary_union

TARGET_CRS = "EPSG:31981"


@dataclass
class ProcessingConfig:
    value_field: str = "VRYIELDMAS"
    harvest_type: str = "pluma"
    source_unit: str = "t_ha"
    global_limit_pct: float = 50.0
    local_radius_m: float = 25.0
    local_limit_pct: float = 25.0
    min_neighbors: int = 5
    max_filter_neighbors: int = 32
    filter_chunk_size: int = 15_000
    pixel_size_m: float = 10.0
    kriging_neighbors: int = 24
    kriging_chunk_size: int = 1_500
    max_variogram_points: int = 2_000
    max_kriging_points: int = 10_000
    max_grid_pixels: int = 350_000


def read_boundary(path: Path) -> gpd.GeoDataFrame:
    boundary = pyogrio.read_dataframe(path)
    if boundary.crs is None:
        raise ValueError("Arquivo de limite sem sistema de coordenadas. Inclua o arquivo .prj.")
    boundary = boundary[boundary.geometry.notna() & ~boundary.geometry.is_empty].copy()
    if boundary.empty:
        raise ValueError("O arquivo de limite não possui geometrias válidas.")
    if not boundary.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("O limite deve ser uma camada poligonal.")
    if boundary.crs.to_string().upper() != TARGET_CRS:
        boundary = boundary.to_crs(TARGET_CRS)
    if not boundary.geometry.is_valid.all():
        boundary.geometry = boundary.geometry.make_valid()
    # Mantém somente geometria para evitar carregar atributos desnecessários.
    return gpd.GeoDataFrame(geometry=boundary.geometry, crs=TARGET_CRS)


def read_harvest_arrays(path: Path, value_field: str, boundary: gpd.GeoDataFrame):
    info = pyogrio.read_info(path)
    if info.get("crs") is None:
        raise ValueError("Arquivo de colheita sem sistema de coordenadas. Inclua o arquivo .prj.")
    fields = list(info.get("fields", []))
    if value_field not in fields:
        available = ", ".join(fields[:30])
        raise ValueError(f"Campo '{value_field}' não encontrado. Campos disponíveis: {available}")

    # Leitura seletiva: apenas produtividade + geometria. Isso evita carregar centenas
    # de MB de colunas do monitor de colheita que não participam do processamento.
    harvest = pyogrio.read_dataframe(path, columns=[value_field], use_arrow=False)
    if harvest.crs is None:
        raise ValueError("Arquivo de colheita sem sistema de coordenadas.")
    harvest = harvest[harvest.geometry.notna() & ~harvest.geometry.is_empty]
    if harvest.empty:
        raise ValueError("A camada de colheita está vazia.")
    if not harvest.geom_type.eq("Point").all():
        raise ValueError("A colheita deve ser uma camada de pontos.")
    if harvest.crs.to_string().upper() != TARGET_CRS:
        harvest = harvest.to_crs(TARGET_CRS)

    x = harvest.geometry.x.to_numpy(dtype=np.float64, copy=True)
    y = harvest.geometry.y.to_numpy(dtype=np.float64, copy=True)
    raw = pd.to_numeric(harvest[value_field], errors="coerce").to_numpy(dtype=np.float64, copy=True)
    original = len(raw)
    del harvest
    gc.collect()

    polygon = unary_union(boundary.geometry.to_numpy())
    inside = contains_xy(polygon, x, y)
    x, y, raw = x[inside], y[inside], raw[inside]
    if len(raw) == 0:
        raise ValueError("Nenhum ponto de colheita está dentro do limite informado.")
    return x, y, raw, original, int(inside.sum())


def convert_yield(values: np.ndarray, unit: str, harvest_type: str) -> np.ndarray:
    divisor = 15.0 if harvest_type == "pluma" else 60.0
    if unit == "t_ha":
        return values * 1000.0 / divisor
    if unit == "kg_ha":
        return values / divisor
    if unit in ("arroba_ha", "sc_ha"):
        return values.astype(np.float64, copy=False)
    raise ValueError("Unidade original não reconhecida.")


def clean_points_arrays(x: np.ndarray, y: np.ndarray, raw: np.ndarray, cfg: ProcessingConfig):
    values = convert_yield(raw, cfg.source_unit, cfg.harvest_type)
    n = len(values)
    # 0=mantido; 1=nulo/zero; 2=global; 3=local
    reason = np.zeros(n, dtype=np.uint8)
    valid = np.isfinite(values) & (values > 0)
    reason[~valid] = 1
    mean = float(np.mean(values[valid])) if np.any(valid) else float("nan")
    if not np.isfinite(mean):
        raise ValueError("Nenhum valor válido foi encontrado no campo escolhido.")

    low = mean * (1 - cfg.global_limit_pct / 100.0)
    high = mean * (1 + cfg.global_limit_pct / 100.0)
    global_bad = valid & ((values < low) | (values > high))
    reason[global_bad] = 2
    kept_global = reason == 0
    kept_ids = np.flatnonzero(kept_global)
    if len(kept_ids) < cfg.min_neighbors + 1:
        raise ValueError("Poucos pontos permaneceram após o filtro global.")

    xy = np.column_stack((x[kept_ids], y[kept_ids]))
    vals = values[kept_ids]
    tree = cKDTree(xy, compact_nodes=True, balanced_tree=True)
    k = min(cfg.max_filter_neighbors + 1, len(kept_ids))
    means = np.full(len(kept_ids), np.nan, dtype=np.float32)
    counts = np.zeros(len(kept_ids), dtype=np.uint16)
    local_bad = np.zeros(len(kept_ids), dtype=bool)

    # Consulta em blocos: a V1 criava matrizes para todos os 370 mil pontos ao mesmo
    # tempo, consumindo mais de 200 MB só no filtro local.
    for start in range(0, len(kept_ids), cfg.filter_chunk_size):
        stop = min(start + cfg.filter_chunk_size, len(kept_ids))
        d, idx = tree.query(
            xy[start:stop],
            k=k,
            distance_upper_bound=cfg.local_radius_m,
            workers=1,
        )
        if k == 1:
            idx = idx[:, None]
            d = d[:, None]
        rows = np.arange(start, stop)[:, None]
        mask = (idx < len(kept_ids)) & (idx != rows)
        safe_idx = np.where(mask, idx, 0)
        neigh_values = vals[safe_idx]
        sums = np.sum(np.where(mask, neigh_values, 0.0), axis=1)
        cnt = np.sum(mask, axis=1)
        local_mean = np.divide(sums, cnt, out=np.full(stop - start, np.nan), where=cnt > 0)
        ok = cnt >= cfg.min_neighbors
        diff = np.zeros(stop - start, dtype=np.float64)
        diff[ok] = np.abs(vals[start:stop][ok] - local_mean[ok]) / local_mean[ok] * 100.0
        means[start:stop] = local_mean.astype(np.float32)
        counts[start:stop] = cnt.astype(np.uint16)
        local_bad[start:stop] = ok & (local_mean > 0) & (diff > cfg.local_limit_pct)
        del d, idx, rows, mask, safe_idx, neigh_values, sums, cnt, local_mean, diff

    reason[kept_ids[local_bad]] = 3
    del tree, xy, vals, kept_global, local_bad
    gc.collect()
    return values, reason, means, counts, kept_ids


def aggregate_points(x: np.ndarray, y: np.ndarray, values: np.ndarray, kept: np.ndarray, cell: float, max_points: int):
    xk, yk, zk = x[kept], y[kept], values[kept]
    gx = np.floor(xk / cell).astype(np.int64)
    gy = np.floor(yk / cell).astype(np.int64)
    keys = np.rec.fromarrays([gx, gy])
    unique, inverse = np.unique(keys, return_inverse=True)
    count = np.bincount(inverse)
    ax = np.bincount(inverse, weights=xk) / count
    ay = np.bincount(inverse, weights=yk) / count
    az = np.bincount(inverse, weights=zk) / count
    xy = np.column_stack((ax, ay))
    if len(xy) > max_points:
        take = np.linspace(0, len(xy) - 1, max_points, dtype=np.int64)
        xy, az = xy[take], az[take]
    del xk, yk, zk, gx, gy, keys, unique, inverse, count, ax, ay
    gc.collect()
    return xy.astype(np.float64, copy=False), az.astype(np.float64, copy=False)


def _models():
    return {
        "esférico": lambda h, nug, sill, rng: nug + (sill - nug) * np.where(h <= rng, 1.5 * (h / rng) - 0.5 * (h / rng) ** 3, 1),
        "exponencial": lambda h, nug, sill, rng: nug + (sill - nug) * (1 - np.exp(-3 * h / rng)),
        "gaussiano": lambda h, nug, sill, rng: nug + (sill - nug) * (1 - np.exp(-3 * (h / rng) ** 2)),
    }


def fit_variogram(xy: np.ndarray, z: np.ndarray, max_points: int):
    rng = np.random.default_rng(42)
    if len(xy) > max_points:
        ids = rng.choice(len(xy), max_points, replace=False)
        p, v = xy[ids], z[ids]
    else:
        p, v = xy, z
    pairs = min(50_000, max(5_000, len(p) * 15))
    i = rng.integers(0, len(p), pairs)
    j = rng.integers(0, len(p), pairs)
    keep = i != j
    i, j = i[keep], j[keep]
    h = np.linalg.norm(p[i] - p[j], axis=1)
    gamma = 0.5 * (v[i] - v[j]) ** 2
    max_h = float(np.quantile(h, 0.8))
    bins = np.linspace(0, max_h, 22)
    centers = (bins[:-1] + bins[1:]) / 2
    b = np.digitize(h, bins) - 1
    gh = np.array([np.nanmedian(gamma[b == k]) if np.any(b == k) else np.nan for k in range(len(centers))])
    ok = np.isfinite(gh) & (centers > 0)
    xx, yy = centers[ok], gh[ok]
    variance = float(np.var(v))
    initial = [max(0, variance * 0.05), max(variance, 1e-6), max(max_h / 3, 10)]
    best = None
    for name, fn in _models().items():
        try:
            popt, _ = curve_fit(
                fn, xx, yy, p0=initial,
                bounds=([0, 1e-9, 5], [max(variance * 2, 1), max(variance * 5, 1), max(max_h * 3, 10)]),
                maxfev=20_000,
            )
            rmse = float(np.sqrt(np.mean((fn(xx, *popt) - yy) ** 2)))
            if best is None or rmse < best[0]:
                best = (rmse, name, popt)
        except Exception:
            pass
    del p, v, i, j, h, gamma, bins, centers, b, gh, xx, yy
    gc.collect()
    if best is None:
        return "exponencial", np.array([variance * 0.05, variance, max(max_h / 3, 50)])
    return best[1], best[2]


def covariance(h: np.ndarray, model: str, params: np.ndarray) -> np.ndarray:
    nug, sill, rng = params
    if model == "esférico":
        corr = np.where(h <= rng, 1 - 1.5 * (h / rng) + 0.5 * (h / rng) ** 3, 0)
    elif model == "gaussiano":
        corr = np.exp(-3 * (h / rng) ** 2)
    else:
        corr = np.exp(-3 * h / rng)
    cov = (sill - nug) * corr
    return np.where(h == 0, sill, cov)


def ordinary_kriging_local(xy, z, targets, model, params, k=24, chunk_size=1500):
    tree = cKDTree(xy, compact_nodes=True, balanced_tree=True)
    k = min(k, len(xy))
    pred = np.empty(len(targets), dtype=np.float32)
    var = np.empty(len(targets), dtype=np.float32)
    for start in range(0, len(targets), chunk_size):
        stop = min(start + chunk_size, len(targets))
        dist, ind = tree.query(targets[start:stop], k=k, workers=1)
        if k == 1:
            pred[start:stop] = z[ind]
            var[start:stop] = 0
            continue
        for local_n, (ids, dt) in enumerate(zip(ind, dist)):
            pts, zz = xy[ids], z[ids]
            D = distance.cdist(pts, pts)
            C = covariance(D, model, params)
            C.flat[:: k + 1] += max(params[1] * 1e-8, 1e-10)
            A = np.empty((k + 1, k + 1))
            A[:k, :k] = C
            A[:k, k] = 1
            A[k, :k] = 1
            A[k, k] = 0
            rhs = np.r_[covariance(dt, model, params), 1.0]
            try:
                sol = np.linalg.solve(A, rhs)
            except np.linalg.LinAlgError:
                sol = np.linalg.lstsq(A, rhs, rcond=None)[0]
            n = start + local_n
            pred[n] = float(sol[:k] @ zz)
            var[n] = max(float(params[1] - sol[:k] @ rhs[:k] + sol[k]), 0)
        del dist, ind
        gc.collect()
    del tree
    return pred, var


def raster_grid(boundary: gpd.GeoDataFrame, pixel: float, max_pixels: int):
    minx, miny, maxx, maxy = boundary.total_bounds
    width = int(math.ceil((maxx - minx) / pixel))
    height = int(math.ceil((maxy - miny) / pixel))
    if width * height > max_pixels:
        suggested = math.ceil(math.sqrt(((maxx - minx) * (maxy - miny)) / max_pixels))
        raise ValueError(f"A grade excede {max_pixels:,} pixels. Aumente o pixel para pelo menos {suggested} m.")
    xs = minx + (np.arange(width) + 0.5) * pixel
    ys = maxy - (np.arange(height) + 0.5) * pixel
    xx, yy = np.meshgrid(xs, ys)
    transform = from_origin(minx, maxy, pixel, pixel)
    mask = geometry_mask([mapping(g) for g in boundary.geometry], out_shape=(height, width), transform=transform, invert=True)
    return xx, yy, mask, transform


def save_outputs(boundary, x, y, values, reason,
                 raster, variance, transform, outdir: Path, model: str,
                 cfg: ProcessingConfig, summary: dict):
    """Grava os resultados sem construir um GeoDataFrame gigante em memória."""
    outdir.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "height": raster.shape[0], "width": raster.shape[1], "count": 1,
        "dtype": "float32", "crs": TARGET_CRS, "transform": transform, "nodata": -9999.0,
        "compress": "deflate", "predictor": 3, "tiled": True,
    }
    with rasterio.open(outdir / "mapa_produtividade.tif", "w", **profile) as dst:
        dst.write(np.where(np.isfinite(raster), raster, -9999).astype("float32"), 1)
    with rasterio.open(outdir / "incerteza_krigagem.tif", "w", **profile) as dst:
        dst.write(np.where(np.isfinite(variance), variance, -9999).astype("float32"), 1)

    gpkg = outdir / "dados_processados.gpkg"
    pyogrio.write_dataframe(boundary, gpkg, layer="limite", driver="GPKG")

    # Apenas pontos mantidos são exportados. A escrita ocorre em blocos para impedir
    # que centenas de milhares de objetos Shapely sejam criados simultaneamente.
    kept_ids = np.flatnonzero(reason == 0)
    export_chunk = 25_000
    first = True
    for start_idx in range(0, len(kept_ids), export_chunk):
        ids = kept_ids[start_idx:start_idx + export_chunk]
        chunk = gpd.GeoDataFrame(
            {"produtividade": values[ids].astype(np.float32, copy=False)},
            geometry=points(x[ids], y[ids]),
            crs=TARGET_CRS,
        )
        pyogrio.write_dataframe(
            chunk, gpkg, layer="pontos_filtrados", driver="GPKG", append=not first
        )
        first = False
        del chunk, ids
        gc.collect()

    (outdir / "resumo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    valid = raster[np.isfinite(raster)]
    if valid.size == 0:
        raise ValueError("A krigagem não produziu pixels válidos dentro do talhão.")
    q = np.quantile(valid, [0, 0.2, 0.4, 0.6, 0.8, 1])
    if float(q[-1] - q[0]) < 1e-9:
        q[-1] = q[0] + 1.0
    cmap = LinearSegmentedColormap.from_list(
        "RdYlGn_custom", ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"], N=256
    )
    # Prévia limpa, em proporção horizontal, sem caixas de texto sobre o mapa.
    # As estatísticas são exibidas separadamente no painel web e no relatório.
    fig, ax = plt.subplots(figsize=(13.33, 7.5), dpi=120)
    extent = [
        transform.c,
        transform.c + transform.a * raster.shape[1],
        transform.f + transform.e * raster.shape[0],
        transform.f,
    ]
    im = ax.imshow(raster, extent=extent, cmap=cmap, origin="upper", vmin=q[0], vmax=q[-1])
    boundary.boundary.plot(ax=ax, color="#26352c", linewidth=1.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Leste (m)", fontsize=10)
    ax.set_ylabel("Norte (m)", fontsize=10)
    ax.tick_params(labelsize=9)
    unit = summary["unit"]
    ax.set_title(
        f"Mapa de Produtividade — média {summary['mean']:.2f} {unit}",
        fontsize=16,
        fontweight="bold",
        pad=12,
    )
    cb = fig.colorbar(im, ax=ax, fraction=0.033, pad=0.025)
    cb.set_label(unit, fontsize=10)
    cb.ax.tick_params(labelsize=9)
    fig.subplots_adjust(left=0.08, right=0.91, bottom=0.12, top=0.90)
    fig.savefig(outdir / "mapa_produtividade.png", facecolor="white", dpi=120)
    plt.close(fig)
    del valid, q, kept_ids
    gc.collect()

def process_yield_map(boundary_path: Path, harvest_path: Path, outdir: Path, cfg: ProcessingConfig) -> dict:
    boundary = read_boundary(boundary_path)
    x, y, raw, original, clipped = read_harvest_arrays(harvest_path, cfg.value_field, boundary)
    values, reason, local_means, local_counts, kept_global_ids = clean_points_arrays(x, y, raw, cfg)
    del raw
    gc.collect()

    kept = reason == 0
    if int(kept.sum()) < 30:
        raise ValueError("Menos de 30 pontos permaneceram após a limpeza.")
    xy, z = aggregate_points(x, y, values, kept, max(cfg.pixel_size_m, 5), cfg.max_kriging_points)
    model, params = fit_variogram(xy, z, cfg.max_variogram_points)
    xx, yy, mask, transform = raster_grid(boundary, cfg.pixel_size_m, cfg.max_grid_pixels)
    targets = np.column_stack((xx[mask], yy[mask]))
    del xx, yy
    gc.collect()

    pred, var = ordinary_kriging_local(xy, z, targets, model, params, cfg.kriging_neighbors, cfg.kriging_chunk_size)
    lo, hi = np.quantile(values[kept], [0.005, 0.995])
    pred = np.clip(pred, lo, hi)
    raster = np.full(mask.shape, np.nan, dtype=np.float32)
    variance = np.full(mask.shape, np.nan, dtype=np.float32)
    raster[mask] = pred
    variance[mask] = var
    del targets, pred, var, xy, z, mask
    gc.collect()

    unit = "@/ha" if cfg.harvest_type == "pluma" else "sc/ha"
    vals = values[kept]
    kept_count = int(kept.sum())
    summary = {
        "version": "2.1-low-memory",
        "original_points": original,
        "clipped_points": clipped,
        "kept_points": kept_count,
        "removed_points": clipped - kept_count,
        "removal_pct": (clipped - kept_count) / clipped * 100,
        "mean": float(np.mean(vals)), "median": float(np.median(vals)),
        "min": float(np.min(vals)), "max": float(np.max(vals)),
        "unit": unit, "crs": TARGET_CRS, "field": cfg.value_field,
        "variogram_model": model,
        "variogram_nugget": float(params[0]), "variogram_sill": float(params[1]), "variogram_range": float(params[2]),
        "pixel_size_m": cfg.pixel_size_m,
        "filter_global_pct": cfg.global_limit_pct,
        "filter_radius_m": cfg.local_radius_m,
        "filter_local_pct": cfg.local_limit_pct,
    }
    del vals, kept, local_means, local_counts, kept_global_ids
    gc.collect()
    save_outputs(boundary, x, y, values, reason,
                 raster, variance, transform, outdir, model, cfg, summary)
    return summary
