from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import math
import warnings
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from scipy.optimize import curve_fit
from scipy.spatial import cKDTree, distance
from shapely.geometry import mapping
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

TARGET_CRS='EPSG:31981'

@dataclass
class ProcessingConfig:
    value_field:str='VRYIELDMAS'
    harvest_type:str='pluma'
    source_unit:str='t_ha'
    global_limit_pct:float=50.0
    local_radius_m:float=25.0
    local_limit_pct:float=25.0
    min_neighbors:int=5
    max_filter_neighbors:int=32
    pixel_size_m:float=10.0
    kriging_neighbors:int=24
    max_variogram_points:int=2500
    max_kriging_points:int=12000


def read_vector(path:Path, expected:str)->gpd.GeoDataFrame:
    gdf=gpd.read_file(path)
    if gdf.crs is None: raise ValueError('Arquivo sem sistema de coordenadas. Inclua o arquivo .prj.')
    gdf=gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy().to_crs(TARGET_CRS)
    if expected=='point' and not gdf.geom_type.isin(['Point']).all(): raise ValueError('A colheita deve ser uma camada de pontos.')
    if expected=='polygon' and not gdf.geom_type.isin(['Polygon','MultiPolygon']).all(): raise ValueError('O limite deve ser uma camada poligonal.')
    if not gdf.geometry.is_valid.all(): gdf.geometry=gdf.geometry.make_valid()
    return gdf


def convert_yield(values:pd.Series, unit:str, harvest_type:str)->pd.Series:
    x=pd.to_numeric(values,errors='coerce')
    divisor=15.0 if harvest_type=='pluma' else 60.0
    if unit=='t_ha': return x*1000.0/divisor
    if unit=='kg_ha': return x/divisor
    if unit in ('arroba_ha','sc_ha'): return x
    raise ValueError('Unidade original não reconhecida.')


def clean_points(gdf:gpd.GeoDataFrame,cfg:ProcessingConfig)->gpd.GeoDataFrame:
    out=gdf.copy()
    out['produtividade']=convert_yield(out[cfg.value_field],cfg.source_unit,cfg.harvest_type)
    out['status']='mantido'; out['motivo']=''; out['media_local']=np.nan; out['n_vizinhos']=0
    invalid=~np.isfinite(out['produtividade'].to_numpy()) | (out['produtividade'].to_numpy()<=0)
    out.loc[invalid,['status','motivo']]=['removido','nulo_ou_zero']
    valid=out.status.eq('mantido')
    mean=float(out.loc[valid,'produtividade'].mean())
    if not np.isfinite(mean): raise ValueError('Nenhum valor válido foi encontrado no campo escolhido.')
    low=mean*(1-cfg.global_limit_pct/100); high=mean*(1+cfg.global_limit_pct/100)
    bad=valid & ~out.produtividade.between(low,high)
    out.loc[bad,['status','motivo']]=['removido','limite_global']
    idx=out.index[out.status.eq('mantido')]
    if len(idx)<cfg.min_neighbors+1: raise ValueError('Poucos pontos permaneceram após o filtro global.')
    xy=np.column_stack((out.loc[idx].geometry.x.to_numpy(),out.loc[idx].geometry.y.to_numpy()))
    vals=out.loc[idx,'produtividade'].to_numpy(float)
    tree=cKDTree(xy)
    k=min(cfg.max_filter_neighbors+1,len(idx))
    d,ii=tree.query(xy,k=k,distance_upper_bound=cfg.local_radius_m,workers=-1)
    means=np.full(len(idx),np.nan); counts=np.zeros(len(idx),dtype=int); local_bad=np.zeros(len(idx),dtype=bool)
    for row in range(len(idx)):
        neigh=ii[row]
        good=(neigh<len(idx)) & (neigh!=row)
        neigh=neigh[good]
        counts[row]=len(neigh)
        if len(neigh)<cfg.min_neighbors: continue
        m=float(np.mean(vals[neigh])); means[row]=m
        if m>0 and abs(vals[row]-m)/m*100>cfg.local_limit_pct: local_bad[row]=True
    out.loc[idx,'media_local']=means; out.loc[idx,'n_vizinhos']=counts
    out.loc[idx[local_bad],['status','motivo']]=['removido','limite_local']
    return out


def aggregate_points(gdf:gpd.GeoDataFrame,cell:float,max_points:int)->tuple[np.ndarray,np.ndarray]:
    w=gdf[gdf.status.eq('mantido')].copy()
    w['gx']=np.floor(w.geometry.x/cell).astype(np.int64); w['gy']=np.floor(w.geometry.y/cell).astype(np.int64)
    a=w.groupby(['gx','gy'],as_index=False).agg(produtividade=('produtividade','mean'),x=('geometry',lambda s:float(np.mean([p.x for p in s]))),y=('geometry',lambda s:float(np.mean([p.y for p in s]))))
    if len(a)>max_points:
        # Amostragem espacial uniforme por quantis de índice para limitar custo da krigagem.
        take=np.linspace(0,len(a)-1,max_points,dtype=int); a=a.iloc[take]
    return a[['x','y']].to_numpy(float),a.produtividade.to_numpy(float)


def _models():
    return {
      'esférico': lambda h,nug,sill,rng: nug+(sill-nug)*np.where(h<=rng,1.5*(h/rng)-.5*(h/rng)**3,1),
      'exponencial': lambda h,nug,sill,rng: nug+(sill-nug)*(1-np.exp(-3*h/rng)),
      'gaussiano': lambda h,nug,sill,rng: nug+(sill-nug)*(1-np.exp(-3*(h/rng)**2)),
    }


def fit_variogram(xy:np.ndarray,z:np.ndarray,max_points:int):
    rng=np.random.default_rng(42)
    if len(xy)>max_points:
        ids=rng.choice(len(xy),max_points,replace=False); p=xy[ids]; v=z[ids]
    else: p=xy; v=z
    # Pares aleatórios evitam matriz quadrática muito grande.
    pairs=min(80000,max(5000,len(p)*20))
    i=rng.integers(0,len(p),pairs); j=rng.integers(0,len(p),pairs); keep=i!=j; i=i[keep];j=j[keep]
    h=np.linalg.norm(p[i]-p[j],axis=1); gamma=.5*(v[i]-v[j])**2
    max_h=float(np.quantile(h,.8)); bins=np.linspace(0,max_h,22); centers=(bins[:-1]+bins[1:])/2
    b=np.digitize(h,bins)-1
    gh=np.array([np.nanmedian(gamma[b==k]) if np.any(b==k) else np.nan for k in range(len(centers))])
    ok=np.isfinite(gh) & (centers>0)
    x=centers[ok]; y=gh[ok]
    variance=float(np.var(v)); initial=[max(0,variance*.05),max(variance,1e-6),max(max_h/3,10)]
    best=None
    for name,fn in _models().items():
        try:
            popt,_=curve_fit(fn,x,y,p0=initial,bounds=([0,1e-9,5],[max(variance*2,1),max(variance*5,1),max_h*3]),maxfev=20000)
            rmse=float(np.sqrt(np.mean((fn(x,*popt)-y)**2)))
            if best is None or rmse<best[0]: best=(rmse,name,popt)
        except Exception: pass
    if best is None: return 'exponencial',np.array([variance*.05,variance,max(max_h/3,50)])
    return best[1],best[2]


def covariance(h:np.ndarray,model:str,params:np.ndarray)->np.ndarray:
    nug,sill,rng=params
    if model=='esférico': corr=np.where(h<=rng,1-1.5*(h/rng)+.5*(h/rng)**3,0)
    elif model=='gaussiano': corr=np.exp(-3*(h/rng)**2)
    else: corr=np.exp(-3*h/rng)
    cov=(sill-nug)*corr
    cov=np.where(h==0,sill,cov)
    return cov


def ordinary_kriging_local(xy,z,targets,model,params,k=24):
    tree=cKDTree(xy); k=min(k,len(xy)); dist,ind=tree.query(targets,k=k,workers=-1)
    if k==1: return z[ind].astype(float),np.zeros(len(targets))
    pred=np.empty(len(targets)); var=np.empty(len(targets))
    for n,(ids,dt) in enumerate(zip(ind,dist)):
        pts=xy[ids]; zz=z[ids]
        D=distance.cdist(pts,pts)
        C=covariance(D,model,params)
        C.flat[::k+1]+=max(params[1]*1e-8,1e-10)
        A=np.empty((k+1,k+1)); A[:k,:k]=C; A[:k,k]=1; A[k,:k]=1; A[k,k]=0
        rhs=np.r_[covariance(dt,model,params),1.0]
        try: sol=np.linalg.solve(A,rhs)
        except np.linalg.LinAlgError: sol=np.linalg.lstsq(A,rhs,rcond=None)[0]
        pred[n]=float(sol[:k]@zz); var[n]=max(float(params[1]-sol[:k]@rhs[:k]+sol[k]),0)
    return pred,var


def raster_grid(boundary:gpd.GeoDataFrame,pixel:float):
    minx,miny,maxx,maxy=boundary.total_bounds
    width=int(math.ceil((maxx-minx)/pixel)); height=int(math.ceil((maxy-miny)/pixel))
    if width*height>400000: raise ValueError('A grade excede 400 mil pixels. Aumente o tamanho do pixel.')
    xs=minx+(np.arange(width)+.5)*pixel; ys=maxy-(np.arange(height)+.5)*pixel
    xx,yy=np.meshgrid(xs,ys); transform=from_origin(minx,maxy,pixel,pixel)
    mask=geometry_mask([mapping(g) for g in boundary.geometry],out_shape=(height,width),transform=transform,invert=True)
    return xx,yy,mask,transform


def save_outputs(boundary,cleaned,raster,variance,transform,outdir:Path,model:str,cfg:ProcessingConfig,summary:dict):
    outdir.mkdir(parents=True,exist_ok=True)
    profile={'driver':'GTiff','height':raster.shape[0],'width':raster.shape[1],'count':1,'dtype':'float32','crs':TARGET_CRS,'transform':transform,'nodata':-9999.0,'compress':'deflate'}
    with rasterio.open(outdir/'mapa_produtividade.tif','w',**profile) as dst: dst.write(np.where(np.isfinite(raster),raster,-9999).astype('float32'),1)
    with rasterio.open(outdir/'incerteza_krigagem.tif','w',**profile) as dst: dst.write(np.where(np.isfinite(variance),variance,-9999).astype('float32'),1)
    gpkg=outdir/'dados_processados.gpkg'
    boundary.to_file(gpkg,layer='limite',driver='GPKG')
    cleaned.to_file(gpkg,layer='colheita_auditada',driver='GPKG')
    (outdir/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    valid=raster[np.isfinite(raster)]
    q=np.quantile(valid,[0,.2,.4,.6,.8,1])
    colors=['#d7191c','#fdae61','#ffffbf','#a6d96a','#1a9641']
    cmap=LinearSegmentedColormap.from_list('RdYlGn_custom',colors,N=256)
    fig,ax=plt.subplots(figsize=(13.33,7.5),dpi=150)
    extent=[transform.c,transform.c+transform.a*raster.shape[1],transform.f+transform.e*raster.shape[0],transform.f]
    im=ax.imshow(raster,extent=extent,cmap=cmap,origin='upper',vmin=q[0],vmax=q[-1])
    boundary.boundary.plot(ax=ax,color='#26352c',linewidth=1.4)
    ax.set_aspect('equal'); ax.set_xlabel('Leste (m)'); ax.set_ylabel('Norte (m)')
    unit=summary['unit']; ax.set_title(f"Mapa de Produtividade — média {summary['mean']:.2f} {unit}",fontsize=16,fontweight='bold')
    cb=fig.colorbar(im,ax=ax,fraction=.035,pad=.025); cb.set_label(unit)
    info=(f"Pontos mantidos: {summary['kept_points']:,}\nPontos removidos: {summary['removed_points']:,} ({summary['removal_pct']:.1f}%)\n"
          f"Krigagem ordinária: {model}\nPixel: {cfg.pixel_size_m:g} m · EPSG:31981")
    ax.text(.012,.018,info,transform=ax.transAxes,fontsize=9,va='bottom',bbox=dict(facecolor='white',alpha=.88,edgecolor='#adb8b0',boxstyle='round,pad=.5'))
    fig.tight_layout(); fig.savefig(outdir/'mapa_produtividade.png',bbox_inches='tight'); plt.close(fig)


def process_yield_map(boundary_path:Path,harvest_path:Path,outdir:Path,cfg:ProcessingConfig)->dict:
    boundary=read_vector(boundary_path,'polygon')
    harvest=read_vector(harvest_path,'point')
    if cfg.value_field not in harvest.columns:
        available=', '.join([c for c in harvest.columns if c!='geometry'][:30])
        raise ValueError(f"Campo '{cfg.value_field}' não encontrado. Campos disponíveis: {available}")
    original=len(harvest)
    harvest=gpd.clip(harvest,boundary)
    clipped=len(harvest)
    if clipped==0: raise ValueError('Nenhum ponto de colheita está dentro do limite informado.')
    cleaned=clean_points(harvest,cfg)
    kept=cleaned[cleaned.status.eq('mantido')]
    if len(kept)<30: raise ValueError('Menos de 30 pontos permaneceram após a limpeza.')
    xy,z=aggregate_points(cleaned,max(cfg.pixel_size_m,5),cfg.max_kriging_points)
    model,params=fit_variogram(xy,z,cfg.max_variogram_points)
    xx,yy,mask,transform=raster_grid(boundary,cfg.pixel_size_m)
    targets=np.column_stack((xx[mask],yy[mask]))
    pred,var=ordinary_kriging_local(xy,z,targets,model,params,cfg.kriging_neighbors)
    # Evita extrapolações numéricas fora da distribuição agronômica observada.
    lo,hi=np.quantile(kept.produtividade,[.005,.995]); pred=np.clip(pred,lo,hi)
    raster=np.full(mask.shape,np.nan); variance=np.full(mask.shape,np.nan); raster[mask]=pred; variance[mask]=var
    unit='@/ha' if cfg.harvest_type=='pluma' else 'sc/ha'
    vals=kept.produtividade.to_numpy(float)
    summary={
      'original_points':original,'clipped_points':clipped,'kept_points':len(kept),'removed_points':clipped-len(kept),
      'removal_pct':(clipped-len(kept))/clipped*100,'mean':float(np.mean(vals)),'median':float(np.median(vals)),
      'min':float(np.min(vals)),'max':float(np.max(vals)),'unit':unit,'crs':TARGET_CRS,'field':cfg.value_field,
      'variogram_model':model,'variogram_nugget':float(params[0]),'variogram_sill':float(params[1]),'variogram_range':float(params[2]),
      'pixel_size_m':cfg.pixel_size_m,'filter_global_pct':cfg.global_limit_pct,'filter_radius_m':cfg.local_radius_m,
      'filter_local_pct':cfg.local_limit_pct
    }
    save_outputs(boundary,cleaned,raster,variance,transform,outdir,model,cfg,summary)
    return summary
