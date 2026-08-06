from __future__ import annotations

import gc
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from agrogeo import (ProcessingConfig, create_yield_pdf, process_yield_map, FertilityConfig, inspect_excel, process_fertility, create_fertility_pdf)

BASE = Path(tempfile.gettempdir()) / "agro-map-jobs"
BASE.mkdir(exist_ok=True)
TTL = int(os.getenv("TEMP_TTL_MINUTES", "30")) * 60
origins_env = os.getenv("ALLOWED_ORIGINS", "*")
origins = [x.strip() for x in origins_env.split(",") if x.strip()]

app = FastAPI(title="Colheita × Fertilidade API", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup():
    now = time.time()
    for p in BASE.iterdir():
        try:
            if p.is_dir() and now - p.stat().st_mtime > TTL:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass
    gc.collect()


def safe_name(name: str) -> str:
    return Path(name or "arquivo").name.replace("..", "_")


async def save_upload_stream(upload: UploadFile, destination: Path, chunk_size: int = 1024 * 1024):
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
    await upload.close()


async def materialize(files: list[UploadFile], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if not files:
        raise HTTPException(400, "Nenhum arquivo foi enviado.")
    for upload in files:
        await save_upload_stream(upload, folder / safe_name(upload.filename or "arquivo"))

    zips = list(folder.glob("*.zip"))
    if zips:
        if len(zips) > 1:
            raise HTTPException(400, "Envie somente um ZIP por camada.")
        extract = folder / "extraido"
        extract.mkdir()
        try:
            with zipfile.ZipFile(zips[0]) as z:
                root = extract.resolve()
                for member in z.infolist():
                    target = (extract / member.filename).resolve()
                    if not str(target).startswith(str(root)):
                        raise HTTPException(400, "ZIP inválido.")
                z.extractall(extract)
        except zipfile.BadZipFile:
            raise HTTPException(400, "O arquivo ZIP está corrompido.")
        search = extract
    else:
        search = folder

    shps = list(search.rglob("*.shp"))
    if len(shps) != 1:
        raise HTTPException(400, "Cada camada deve conter exatamente um arquivo .shp.")
    base = shps[0].with_suffix("")
    missing = [ext for ext in (".shx", ".dbf") if not base.with_suffix(ext).exists()]
    if missing:
        raise HTTPException(400, f"Faltam componentes obrigatórios: {', '.join(missing)}")
    return shps[0]


@app.get("/")
def root():
    return {"service": "Colheita × Fertilidade API", "status": "online", "docs": "/docs"}


@app.get("/health")
def health():
    cleanup()
    return {"status": "ok", "version": "3.1.0-fertility-bins-fix", "temporary_ttl_minutes": TTL // 60}


@app.post("/process-yield")
async def process_yield(
    boundary_files: Annotated[list[UploadFile], File(...)],
    harvest_files: Annotated[list[UploadFile], File(...)],
    value_field: Annotated[str, Form()] = "VRYIELDMAS",
    harvest_type: Annotated[str, Form()] = "pluma",
    source_unit: Annotated[str, Form()] = "t_ha",
    global_limit_pct: Annotated[float, Form()] = 50,
    local_radius_m: Annotated[float, Form()] = 25,
    local_limit_pct: Annotated[float, Form()] = 25,
    pixel_size_m: Annotated[float, Form()] = 10,
    unidade: Annotated[str, Form()] = "",
    fazenda: Annotated[str, Form()] = "",
    talhao: Annotated[str, Form()] = "",
    data_plantio: Annotated[str, Form()] = "",
    variedade: Annotated[str, Form()] = "",
):
    cleanup()
    job_id = uuid.uuid4().hex
    job = BASE / job_id
    job.mkdir()
    try:
        boundary = await materialize(boundary_files, job / "boundary")
        harvest = await materialize(harvest_files, job / "harvest")
        cfg = ProcessingConfig(
            value_field=value_field.strip(), harvest_type=harvest_type, source_unit=source_unit,
            global_limit_pct=global_limit_pct, local_radius_m=local_radius_m,
            local_limit_pct=local_limit_pct, pixel_size_m=pixel_size_m,
        )
        summary = process_yield_map(boundary, harvest, job / "output", cfg)
        report_metadata = {
            "unidade": unidade.strip(),
            "fazenda": fazenda.strip(),
            "talhao": talhao.strip(),
            "data_plantio": data_plantio.strip(),
            "variedade": variedade.strip(),
        }
        summary["report_metadata"] = report_metadata
        create_yield_pdf(job / "output", summary, report_metadata)
        # Atualiza o JSON para incluir também os dados de identificação.
        import json
        (job / "output" / "resumo.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.make_archive(str(job / "resultado_mapa_produtividade"), "zip", job / "output")
        gc.collect()
        return {
            "job_id": job_id,
            "summary": summary,
            "preview_url": f"/jobs/{job_id}/preview",
            "pdf_url": f"/jobs/{job_id}/pdf",
            "download_url": f"/jobs/{job_id}/download",
        }
    except HTTPException:
        shutil.rmtree(job, ignore_errors=True)
        raise
    except ValueError as exc:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(400, str(exc))
    except MemoryError:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(507, "Memória insuficiente. Aumente o pixel do mapa ou use uma instância com mais RAM.")
    except Exception as exc:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(500, f"Falha durante o processamento: {type(exc).__name__}: {exc}")
    finally:
        gc.collect()


@app.get("/jobs/{job_id}/preview")
def preview(job_id: str):
    path = BASE / job_id / "output" / "mapa_produtividade.png"
    if not path.exists():
        raise HTTPException(404, "Resultado expirado ou inexistente.")
    return FileResponse(path, media_type="image/png")


@app.get("/jobs/{job_id}/pdf")
def pdf(job_id: str):
    path = BASE / job_id / "output" / "relatorio_mapa_produtividade.pdf"
    if not path.exists():
        raise HTTPException(404, "Relatório expirado ou inexistente.")
    return FileResponse(
        path,
        filename="relatorio_mapa_produtividade.pdf",
        media_type="application/pdf",
    )


@app.get("/jobs/{job_id}/download")
def download(job_id: str):
    path = BASE / job_id / "resultado_mapa_produtividade.zip"
    if not path.exists():
        raise HTTPException(404, "Resultado expirado ou inexistente.")
    return FileResponse(path, filename="resultado_mapa_produtividade.zip", media_type="application/zip")


@app.post("/inspect-fertility")
async def inspect_fertility(file: UploadFile = File(...)):
    cleanup()
    folder=Path(tempfile.mkdtemp(prefix="fert-inspect-",dir=BASE))
    try:
        path=folder/safe_name(file.filename or "analise.xlsx")
        await save_upload_stream(file,path)
        return inspect_excel(path)
    except Exception as exc:
        raise HTTPException(400,f"Não foi possível ler a planilha: {exc}")
    finally:
        shutil.rmtree(folder,ignore_errors=True)

@app.post("/jobs/{job_id}/process-fertility")
async def process_fertility_job(
    job_id: str,
    file: UploadFile = File(...),
    attributes_json: str = Form(...),
    latitude_field: str = Form("Latitude"),
    longitude_field: str = Form("Longitude"),
    point_id_field: str = Form("Ponto"),
    idw_power: float = Form(3.0),
    pixel_size_m: float = Form(10.0),
    buffer_radius_m: float = Form(50.0),
):
    cleanup(); job=BASE/job_id
    if not (job/"output"/"mapa_produtividade.tif").exists(): raise HTTPException(404,"Mapa de colheita expirado ou inexistente.")
    try:
        import json
        attrs=json.loads(attributes_json)
        if not isinstance(attrs,list) or not attrs: raise ValueError("Selecione ao menos um atributo.")
        fert=job/"fertility"; fert.mkdir(exist_ok=True)
        excel=fert/safe_name(file.filename or "analise.xlsx"); await save_upload_stream(file,excel)
        cfg=FertilityConfig(latitude_field=latitude_field,longitude_field=longitude_field,point_id_field=point_id_field,idw_power=idw_power,pixel_size_m=pixel_size_m,buffer_radius_m=buffer_radius_m)
        summary=process_fertility(excel,job/"output",fert/"output",attrs,cfg)
        yield_summary=json.loads((job/"output"/"resumo.json").read_text(encoding="utf-8"))
        metadata=yield_summary.get("report_metadata",{})
        create_fertility_pdf(job/"output",fert/"output",metadata,summary)
        shutil.make_archive(str(fert/"resultado_fertilidade"),"zip",fert/"output")
        return {"job_id":job_id,"summary":summary,"pdf_url":f"/jobs/{job_id}/fertility/pdf","download_url":f"/jobs/{job_id}/fertility/download","attributes":[{**a,"map_url":f"/jobs/{job_id}/fertility/files/{a['map_url']}","scatter_url":f"/jobs/{job_id}/fertility/files/{a['scatter_url']}"} for a in summary['attributes']]}
    except ValueError as exc: raise HTTPException(400,str(exc))
    except Exception as exc: raise HTTPException(500,f"Falha na fertilidade: {type(exc).__name__}: {exc}")

@app.get("/jobs/{job_id}/fertility/files/{filename}")
def fertility_file(job_id: str, filename: str):
    path=BASE/job_id/"fertility"/"output"/safe_name(filename)
    if not path.exists(): raise HTTPException(404,"Arquivo expirado ou inexistente.")
    media="image/png" if path.suffix.lower()==".png" else "application/octet-stream"
    return FileResponse(path,media_type=media)

@app.get("/jobs/{job_id}/fertility/pdf")
def fertility_pdf(job_id: str):
    path=BASE/job_id/"fertility"/"output"/"relatorio_colheita_fertilidade.pdf"
    if not path.exists(): raise HTTPException(404,"Relatório expirado ou inexistente.")
    return FileResponse(path,filename="relatorio_colheita_fertilidade.pdf",media_type="application/pdf")

@app.get("/jobs/{job_id}/fertility/download")
def fertility_download(job_id: str):
    path=BASE/job_id/"fertility"/"resultado_fertilidade.zip"
    if not path.exists(): raise HTTPException(404,"Resultado expirado ou inexistente.")
    return FileResponse(path,filename="resultado_fertilidade.zip",media_type="application/zip")
