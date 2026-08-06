from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gc, json, math, re

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from scipy.spatial import cKDTree
from scipy.stats import pearsonr, spearmanr
from shapely.geometry import mapping

TARGET_CRS = "EPSG:31981"

@dataclass
class FertilityConfig:
    latitude_field: str = "Latitude"
    longitude_field: str = "Longitude"
    point_id_field: str = "Ponto"
    idw_power: float = 3.0
    pixel_size_m: float = 10.0
    buffer_radius_m: float = 50.0
    max_grid_pixels: int = 1_500_000

PRESETS = {
    "Argila [g/kg]": ([0,150,200,250,300,400,1000], "Argila", "%"),
    "M.O. [g/dm³]": ([-1e9,18,26,34,42,1e9], "M.O.", "g/dm³"),
    "C.T.C. [mmolc/dm³]": ([-1e9,47,64,81,98,1e9], "C.T.C.", "mmolc/dm³"),
    "V% [%]": ([-1e9,10,20,30,40,50,60,70,80,1e9], "V%", "%"),
    "P (r) [mg/dm³]": ([-1e9,8,13,18,23,1e9], "P (r)", "mg/dm³"),
    "Ca [cmolc/dm³]": ([-1e9,1.2,1.9,2.6,3.3,1e9], "Ca", "cmolc/dm³"),
    "Mg [cmolc/dm³]": ([-1e9,.56,.92,1.28,1.64,1e9], "Mg", "cmolc/dm³"),
    "K [ppm]": ([-1e9,56,72,88,104,1e9], "K", "ppm"),
    "S [mg/dm³]": ([-1e9,9,13,17,21,1e9], "S", "mg/dm³"),
    "B [mg/dm³]": ([-1e9,.3,.6,.9,1.2,1e9], "B", "mg/dm³"),
    "Zn [mg/dm³]": ([-1e9,.6,1,1.4,1.8,1e9], "Zn", "mg/dm³"),
    "Fe [mg/dm³]": ([-1e9,50,75,100,125,1e9], "Fe", "mg/dm³"),
    "Mn [mg/dm³]": ([-1e9,4.8,7.6,10.4,13.2,1e9], "Mn", "mg/dm³"),
    "Cu [mg/dm³]": ([-1e9,.5,1,1.5,2,1e9], "Cu", "mg/dm³"),
    "H° + Al³ [mmolc/dm³]": ([-1e9,40,60,80,100,1e9], "H + Al", "mmolc/dm³"),
    "Al³ [mmolc/dm³]": ([-1e9,1,2,3,4,1e9], "Al", "mmolc/dm³"),
    "Ca na CTC [%]": ([-1e9,10,15,20,25,30,35,40,1e9], "Ca na CTC", "%"),
    "Mg na CTC [%]": ([-1e9,10,15,20,25,1e9], "Mg na CTC", "%"),
    "K na CTC [%]": ([-1e9,2,3,4,5,1e9], "K na CTC", "%"),
}

def _slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:60] or "atributo"

def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False).replace({"-": np.nan, "": np.nan}), errors="coerce")

def inspect_excel(path: Path) -> dict:
    xls = pd.ExcelFile(path)
    sheet = xls.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, nrows=50)
    columns = [str(c).strip() for c in df.columns]
    low = {c.lower(): c for c in columns}
    lat = next((low[k] for k in low if "latitude" in k or k in {"lat","y"}), columns[0] if columns else "")
    lon = next((low[k] for k in low if "longitude" in k or k in {"lon","long","x"}), columns[1] if len(columns)>1 else "")
    excluded = {lat, lon, "Produtor", "Fazenda", "Talhão", "Data da Amostra", "Ponto", "Profundidade"}
    numeric=[]
    for c in columns:
        if c in excluded: continue
        if _numeric(df[c]).notna().sum() >= max(2, len(df)//4): numeric.append(c)
    return {"sheet": sheet, "columns": columns, "numeric_columns": numeric, "latitude_field": lat, "longitude_field": lon, "point_id_field": "Ponto" if "Ponto" in columns else ""}

def _read_samples(path: Path, cfg: FertilityConfig, attrs: list[str]) -> gpd.GeoDataFrame:
    df = pd.read_excel(path)
    required=[cfg.latitude_field,cfg.longitude_field]
    missing=[c for c in required if c not in df.columns]
    if missing: raise ValueError(f"Colunas de coordenadas não encontradas: {', '.join(missing)}")
    keep=[c for c in [cfg.point_id_field,cfg.latitude_field,cfg.longitude_field,*attrs] if c and c in df.columns]
    df=df[keep].copy()
    lat=_numeric(df[cfg.latitude_field]); lon=_numeric(df[cfg.longitude_field])
    valid=lat.between(-90,90)&lon.between(-180,180)
    df=df.loc[valid].copy(); lat=lat.loc[valid]; lon=lon.loc[valid]
    for c in attrs: df[c]=_numeric(df[c])
    # Conversões agronômicas para atributos selecionados.
    if "K [mmolc/dm³]" in df.columns:
        df["K [ppm]"] = df["K [mmolc/dm³]"] * 39.1
    if "Ca [mmolc/dm³]" in df.columns:
        df["Ca [cmolc/dm³]"] = df["Ca [mmolc/dm³]"] / 10.0
    if "Mg [mmolc/dm³]" in df.columns:
        df["Mg [cmolc/dm³]"] = df["Mg [mmolc/dm³]"] / 10.0
    gdf=gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(lon,lat), crs="EPSG:4326").to_crs(TARGET_CRS)
    if len(gdf)<3: raise ValueError("São necessários pelo menos 3 pontos válidos de fertilidade.")
    return gdf

def _idw(xy: np.ndarray, z: np.ndarray, targets: np.ndarray, power: float, k: int=12, chunk: int=50000) -> np.ndarray:
    tree=cKDTree(xy); out=np.empty(len(targets),dtype=np.float32)
    kk=min(k,len(xy))
    for start in range(0,len(targets),chunk):
        t=targets[start:start+chunk]
        d,idx=tree.query(t,k=kk,workers=1)
        if kk==1: d=d[:,None]; idx=idx[:,None]
        d=np.maximum(d,1e-6); w=1.0/np.power(d,power)
        out[start:start+len(t)]=(np.sum(w*z[idx],axis=1)/np.sum(w,axis=1)).astype(np.float32)
    return out

def _grid(boundary: gpd.GeoDataFrame, pixel: float, max_pixels: int):
    minx,miny,maxx,maxy=boundary.total_bounds
    width=int(math.ceil((maxx-minx)/pixel)); height=int(math.ceil((maxy-miny)/pixel))
    if width*height>max_pixels: raise ValueError("Grade da fertilidade muito grande. Aumente o pixel.")
    xs=minx+(np.arange(width)+.5)*pixel; ys=maxy-(np.arange(height)+.5)*pixel
    xx,yy=np.meshgrid(xs,ys); transform=from_origin(minx,maxy,pixel,pixel)
    mask=geometry_mask([mapping(g) for g in boundary.geometry],out_shape=(height,width),transform=transform,invert=True)
    return xx,yy,mask,transform

def _yield_means(samples: gpd.GeoDataFrame, yield_tif: Path, radius: float) -> np.ndarray:
    vals=[]
    with rasterio.open(yield_tif) as src:
        arr=src.read(1,masked=True)
        for geom in samples.geometry:
            row,col=src.index(geom.x,geom.y)
            px=max(abs(src.transform.a),abs(src.transform.e)); r=max(1,int(math.ceil(radius/px)))
            r0=max(0,row-r); r1=min(src.height,row+r+1); c0=max(0,col-r); c1=min(src.width,col+r+1)
            win=arr[r0:r1,c0:c1]
            rr,cc=np.mgrid[r0:r1,c0:c1]
            xs=src.transform.c+(cc+.5)*src.transform.a
            ys=src.transform.f+(rr+.5)*src.transform.e
            mask=((xs-geom.x)**2+(ys-geom.y)**2)<=radius**2
            data=np.asarray(win.filled(np.nan),dtype=float)[mask]
            data=data[np.isfinite(data)&(data!=src.nodata)]
            vals.append(float(np.mean(data)) if data.size else np.nan)
    return np.asarray(vals,dtype=float)

def _preset(attr: str, values: np.ndarray):
    if attr in PRESETS: return PRESETS[attr]
    q=np.unique(np.quantile(values[np.isfinite(values)],[0,.2,.4,.6,.8,1]))
    if len(q)<3: q=np.array([np.nanmin(values),np.nanmean(values),np.nanmax(values)+1e-6])
    return (q.tolist(), attr.split("[")[0].strip(), attr[attr.find("[")+1:attr.find("]")] if "[" in attr else "")

def _safe_legend_bins(raw_bins, raster: np.ndarray) -> np.ndarray:
    """Retorna limites estritamente crescentes para o BoundaryNorm.

    Os presets usam sentinelas abertas (-1e9 e 1e9). A implementação anterior
    substituía essas sentinelas diretamente pelo mínimo e máximo do raster.
    Quando todos os valores ficavam acima da primeira classe (por exemplo K em
    ppm > 104) ou o mínimo coincidia com um limite (por exemplo P(r) = 8), a
    sequência podia virar [109, 56, 72, ...] e o Matplotlib gerava o erro
    "bins must be monotonically increasing or decreasing".
    """
    data = np.asarray(raster, dtype=float)
    data = data[np.isfinite(data)]
    if data.size == 0:
        raise ValueError("O raster interpolado não possui valores válidos para gerar a legenda.")

    bins = np.asarray(raw_bins, dtype=float).copy()
    bins = bins[np.isfinite(bins)]
    if bins.size < 2:
        lo = float(np.nanmin(data)); hi = float(np.nanmax(data))
        if math.isclose(lo, hi): hi = lo + 1e-6
        return np.array([lo - 1e-6, hi + 1e-6], dtype=float)

    data_min = float(np.nanmin(data)); data_max = float(np.nanmax(data))
    eps = max(1e-6, abs(data_max - data_min) * 1e-9)

    # Mantém os limites agronômicos internos e abre as extremidades o suficiente
    # para abranger todos os valores, sem inverter a ordem dos bins.
    if bins[0] < -1e8:
        first_internal = bins[1]
        bins[0] = min(data_min - eps, first_internal - eps)
    if bins[-1] > 1e8:
        last_internal = bins[-2]
        bins[-1] = max(data_max + eps, last_internal + eps)

    # Remove repetições e garante estrita monotonicidade.
    bins = np.unique(bins)
    if bins.size < 2 or not np.all(np.diff(bins) > 0):
        lo = min(data_min, float(np.nanmin(bins)))
        hi = max(data_max, float(np.nanmax(bins)))
        if math.isclose(lo, hi): hi = lo + 1e-6
        bins = np.linspace(lo - eps, hi + eps, 6)
    return bins

def _plot_nutrient(boundary, samples, attr, raster, transform, outpath: Path):
    vals=samples[attr].to_numpy(float); bins,title,unit=_preset(attr,vals)
    finite_bins=_safe_legend_bins(bins,raster)
    cmap=LinearSegmentedColormap.from_list("fert",["#d7191c","#fdae61","#ffffbf","#a6d96a","#1a9641"],N=max(5,len(finite_bins)-1))
    norm=BoundaryNorm(finite_bins,cmap.N,clip=True)
    fig=plt.figure(figsize=(13.33,7.5),dpi=120,facecolor="white")
    ax=fig.add_axes([.09,.12,.72,.76]); cax=fig.add_axes([.84,.18,.022,.64])
    extent=[transform.c,transform.c+transform.a*raster.shape[1],transform.f+transform.e*raster.shape[0],transform.f]
    im=ax.imshow(raster,extent=extent,origin="upper",cmap=cmap,norm=norm)
    boundary.boundary.plot(ax=ax,color="#26352c",linewidth=1.6)
    samples.plot(ax=ax,color="#1554a0",markersize=22,edgecolor="white",linewidth=.6)
    for _,r in samples.iterrows():
        if pd.notna(r[attr]): ax.annotate(f"{r[attr]:.2f}",(r.geometry.x,r.geometry.y),xytext=(4,4),textcoords="offset points",fontsize=7,color="#13251b",path_effects=[])
    minx,miny,maxx,maxy=boundary.total_bounds; padx=(maxx-minx)*.07; pady=(maxy-miny)*.07
    ax.set_xlim(minx-padx,maxx+padx); ax.set_ylim(miny-pady,maxy+pady); ax.set_aspect("equal")
    ax.set_xlabel("Leste (m)"); ax.set_ylabel("Norte (m)")
    fig.suptitle(f"Mapa de Fertilidade — {title} — média {np.nanmean(vals):.2f} {unit}",fontsize=16,fontweight="bold",y=.95)
    cb=fig.colorbar(im,cax=cax,boundaries=finite_bins); cb.set_label(unit)
    fig.savefig(outpath,dpi=130,facecolor="white"); plt.close(fig)

def _scatter(samples, attr, unit_yield, outpath):
    x=samples[attr].to_numpy(float); y=samples["produtividade_50m"].to_numpy(float)
    ok=np.isfinite(x)&np.isfinite(y); x=x[ok]; y=y[ok]
    fig,ax=plt.subplots(figsize=(5.8,3.2),dpi=140)
    ax.scatter(x,y,facecolors="none",edgecolors="#1c6376")
    if len(x)>=2 and np.ptp(x)>0:
        m,b=np.polyfit(x,y,1); xx=np.linspace(x.min(),x.max(),100); ax.plot(xx,m*xx+b,"--",linewidth=1.3)
    ax.set_xlabel(attr); ax.set_ylabel(f"Produtividade média 50 m ({unit_yield})"); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(outpath,facecolor="white"); plt.close(fig)

def process_fertility(excel_path: Path, yield_output: Path, outdir: Path, attrs: list[str], cfg: FertilityConfig) -> dict:
    boundary=gpd.read_file(yield_output/"dados_processados.gpkg",layer="limite").to_crs(TARGET_CRS)
    samples=_read_samples(excel_path,cfg,attrs)
    samples=gpd.clip(samples,boundary)
    if samples.empty: raise ValueError("Nenhum ponto de solo ficou dentro do limite do talhão.")
    converted=[]
    if "K [mmolc/dm³]" in attrs and "K [ppm]" in samples: converted.append("K [ppm]")
    if "Ca [mmolc/dm³]" in attrs and "Ca [cmolc/dm³]" in samples: converted.append("Ca [cmolc/dm³]")
    if "Mg [mmolc/dm³]" in attrs and "Mg [cmolc/dm³]" in samples: converted.append("Mg [cmolc/dm³]")
    final_attrs=[]
    for a in attrs:
        if a=="K [mmolc/dm³]": final_attrs.append("K [ppm]")
        elif a=="Ca [mmolc/dm³]": final_attrs.append("Ca [cmolc/dm³]")
        elif a=="Mg [mmolc/dm³]": final_attrs.append("Mg [cmolc/dm³]")
        else: final_attrs.append(a)
    final_attrs=[a for a in dict.fromkeys(final_attrs) if a in samples.columns and samples[a].notna().sum()>=3]
    if not final_attrs: raise ValueError("Nenhum atributo selecionado possui pelo menos 3 valores numéricos válidos.")
    samples["produtividade_50m"]=_yield_means(samples,yield_output/"mapa_produtividade.tif",cfg.buffer_radius_m)
    xx,yy,mask,transform=_grid(boundary,cfg.pixel_size_m,cfg.max_grid_pixels)
    targets=np.column_stack((xx[mask],yy[mask])); del xx,yy; gc.collect()
    outdir.mkdir(parents=True,exist_ok=True)
    results=[]
    with open(yield_output/"resumo.json",encoding="utf-8") as f: yield_summary=json.load(f)
    for attr in final_attrs:
        valid=samples[attr].notna(); xy=np.column_stack((samples.geometry.x[valid],samples.geometry.y[valid])); z=samples.loc[valid,attr].to_numpy(float)
        pred=_idw(xy,z,targets,cfg.idw_power)
        raster=np.full(mask.shape,np.nan,dtype=np.float32); raster[mask]=pred
        profile={"driver":"GTiff","height":raster.shape[0],"width":raster.shape[1],"count":1,"dtype":"float32","crs":TARGET_CRS,"transform":transform,"nodata":-9999.0,"compress":"deflate","tiled":True}
        slug=_slug(attr)
        with rasterio.open(outdir/f"fertilidade_{slug}.tif","w",**profile) as dst: dst.write(np.where(np.isfinite(raster),raster,-9999).astype("float32"),1)
        _plot_nutrient(boundary,samples,attr,raster,transform,outdir/f"fertilidade_{slug}.png")
        _scatter(samples,attr,yield_summary.get("unit",""),outdir/f"dispersao_{slug}.png")
        x=samples[attr].to_numpy(float); y=samples["produtividade_50m"].to_numpy(float); ok=np.isfinite(x)&np.isfinite(y)
        pear=float(pearsonr(x[ok],y[ok]).statistic) if ok.sum()>=3 and np.ptp(x[ok])>0 and np.ptp(y[ok])>0 else None
        spear=float(spearmanr(x[ok],y[ok]).statistic) if ok.sum()>=3 and np.ptp(x[ok])>0 and np.ptp(y[ok])>0 else None
        r2=pear**2 if pear is not None else None
        results.append({"attribute":attr,"slug":slug,"mean":float(np.nanmean(x)),"min":float(np.nanmin(x)),"max":float(np.nanmax(x)),"pearson":pear,"spearman":spear,"r2":r2,"map_url":f"fertilidade_{slug}.png","scatter_url":f"dispersao_{slug}.png"})
        del raster,pred; gc.collect()
    export_cols=[c for c in [cfg.point_id_field,cfg.latitude_field,cfg.longitude_field,*final_attrs,"produtividade_50m","geometry"] if c in samples.columns]
    samples[export_cols].to_file(outdir/"fertilidade_processada.gpkg",layer="amostras",driver="GPKG")
    summary={"version":"3.1-fertility","attributes":results,"sample_points":len(samples),"buffer_radius_m":cfg.buffer_radius_m,"idw_power":cfg.idw_power,"pixel_size_m":cfg.pixel_size_m,"crs":TARGET_CRS}
    (outdir/"resumo_fertilidade.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary
