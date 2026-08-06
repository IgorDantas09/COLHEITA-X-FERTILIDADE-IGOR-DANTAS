from __future__ import annotations
import os, shutil, tempfile, time, uuid, zipfile
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from agrogeo import ProcessingConfig, process_yield_map

BASE=Path(tempfile.gettempdir())/'agro-map-jobs'; BASE.mkdir(exist_ok=True)
TTL=int(os.getenv('TEMP_TTL_MINUTES','30'))*60
origins=[x.strip() for x in os.getenv('ALLOWED_ORIGINS','http://localhost:3000').split(',') if x.strip()]
app=FastAPI(title='Colheita × Fertilidade API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['*'],allow_headers=['*'])

def cleanup():
    now=time.time()
    for p in BASE.iterdir():
        try:
            if p.is_dir() and now-p.stat().st_mtime>TTL: shutil.rmtree(p,ignore_errors=True)
        except OSError: pass

def safe_name(name:str)->str: return Path(name or 'arquivo').name.replace('..','_')

async def materialize(files:list[UploadFile],folder:Path)->Path:
    folder.mkdir(parents=True,exist_ok=True)
    if not files: raise HTTPException(400,'Nenhum arquivo foi enviado.')
    for f in files:
        dest=folder/safe_name(f.filename or 'arquivo')
        with dest.open('wb') as out: shutil.copyfileobj(f.file,out)
    zips=list(folder.glob('*.zip'))
    if zips:
        if len(zips)>1: raise HTTPException(400,'Envie somente um ZIP por camada.')
        extract=folder/'extraido'; extract.mkdir()
        try:
            with zipfile.ZipFile(zips[0]) as z:
                for member in z.infolist():
                    target=(extract/member.filename).resolve()
                    if not str(target).startswith(str(extract.resolve())): raise HTTPException(400,'ZIP inválido.')
                z.extractall(extract)
        except zipfile.BadZipFile: raise HTTPException(400,'O arquivo ZIP está corrompido.')
        search=extract
    else: search=folder
    shps=list(search.rglob('*.shp'))
    if len(shps)!=1: raise HTTPException(400,'Cada camada deve conter exatamente um arquivo .shp.')
    base=shps[0].with_suffix('')
    missing=[ext for ext in ('.shx','.dbf') if not base.with_suffix(ext).exists()]
    if missing: raise HTTPException(400,f"Faltam componentes obrigatórios: {', '.join(missing)}")
    return shps[0]

@app.get('/health')
def health(): cleanup(); return {'status':'ok','temporary_ttl_minutes':TTL//60}

@app.post('/process-yield')
async def process_yield(
    boundary_files:Annotated[list[UploadFile],File(...)],
    harvest_files:Annotated[list[UploadFile],File(...)],
    value_field:Annotated[str,Form()]='VRYIELDMAS',
    harvest_type:Annotated[str,Form()]='pluma',
    source_unit:Annotated[str,Form()]='t_ha',
    global_limit_pct:Annotated[float,Form()]=50,
    local_radius_m:Annotated[float,Form()]=25,
    local_limit_pct:Annotated[float,Form()]=25,
    pixel_size_m:Annotated[float,Form()]=10,
):
    cleanup(); job_id=uuid.uuid4().hex; job=BASE/job_id; job.mkdir()
    try:
        b=await materialize(boundary_files,job/'boundary')
        h=await materialize(harvest_files,job/'harvest')
        cfg=ProcessingConfig(value_field=value_field.strip(),harvest_type=harvest_type,source_unit=source_unit,
            global_limit_pct=global_limit_pct,local_radius_m=local_radius_m,local_limit_pct=local_limit_pct,pixel_size_m=pixel_size_m)
        summary=process_yield_map(b,h,job/'output',cfg)
        archive=shutil.make_archive(str(job/'resultado_mapa_produtividade'),'zip',job/'output')
        return {'job_id':job_id,'summary':summary,'preview_url':f'/jobs/{job_id}/preview','download_url':f'/jobs/{job_id}/download'}
    except HTTPException: shutil.rmtree(job,ignore_errors=True); raise
    except ValueError as exc: shutil.rmtree(job,ignore_errors=True); raise HTTPException(400,str(exc))
    except Exception as exc:
        shutil.rmtree(job,ignore_errors=True)
        raise HTTPException(500,f'Falha durante o processamento: {type(exc).__name__}: {exc}')

@app.get('/jobs/{job_id}/preview')
def preview(job_id:str):
    path=BASE/job_id/'output'/'mapa_produtividade.png'
    if not path.exists(): raise HTTPException(404,'Resultado expirado ou inexistente.')
    return FileResponse(path,media_type='image/png')

@app.get('/jobs/{job_id}/download')
def download(job_id:str):
    path=BASE/job_id/'resultado_mapa_produtividade.zip'
    if not path.exists(): raise HTTPException(404,'Resultado expirado ou inexistente.')
    return FileResponse(path,filename='resultado_mapa_produtividade.zip',media_type='application/zip')
