'use client';
import {FormEvent, useState} from 'react';

type Result = {
  job_id:string;
  summary:{
    original_points:number; clipped_points:number; kept_points:number; removed_points:number;
    removal_pct:number; mean:number; median:number; min:number; max:number; unit:string;
    crs:string; field:string; variogram_model:string; pixel_size_m:number;
  };
  preview_url:string;
  download_url:string;
};

export default function Page(){
  const api=(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/,'');
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState<Result|null>(null);

  async function submit(e:FormEvent<HTMLFormElement>){
    e.preventDefault(); setLoading(true); setError(''); setResult(null);
    try {
      const fd=new FormData(e.currentTarget);
      const response=await fetch(`${api}/process-yield`,{method:'POST',body:fd});
      const contentType=response.headers.get('content-type') || '';
      const data=contentType.includes('application/json') ? await response.json() : {detail: await response.text()};
      if(!response.ok) throw new Error(data.detail || 'Não foi possível processar os arquivos.');
      setResult(data);
    } catch(err){ setError(err instanceof Error ? err.message : 'Erro inesperado.'); }
    finally{ setLoading(false); }
  }

  const s=result?.summary;
  return <>
    <header className="header"><div className="header-inner"><div className="brand">Colheita × Fertilidade</div><div className="badge">Versão 2 · Baixo consumo de memória</div></div></header>
    <main>
      <section className="hero"><h1>Processamento do mapa de colheita</h1><p>Envie a colheita e o limite do talhão. O sistema limpa os pontos, executa a krigagem e gera o primeiro mapa.</p></section>
      <div className="grid">
        <section className="card"><h2>1. Arquivos e parâmetros</h2>
          <form className="form" onSubmit={submit}>
            <label>Limite do talhão
              <input required name="boundary_files" type="file" multiple accept=".zip,.shp,.shx,.dbf,.prj,.cpg" />
              <small>Selecione um ZIP ou, juntos, os arquivos SHP, SHX, DBF e PRJ.</small>
            </label>
            <label>Dados de colheita
              <input required name="harvest_files" type="file" multiple accept=".zip,.shp,.shx,.dbf,.prj,.cpg" />
              <small>O shapefile deve ser uma camada de pontos.</small>
            </label>
            <div className="row">
              <label>Campo de produtividade<input name="value_field" defaultValue="VRYIELDMAS" /></label>
              <label>Tipo de colheita<select name="harvest_type" defaultValue="pluma"><option value="pluma">Pluma de algodão (@/ha)</option><option value="grao">Grão (sc/ha)</option></select></label>
            </div>
            <div className="row">
              <label>Unidade original<select name="source_unit" defaultValue="t_ha"><option value="t_ha">Toneladas/hectare</option><option value="kg_ha">Quilogramas/hectare</option><option value="arroba_ha">Arrobas/hectare</option><option value="sc_ha">Sacas/hectare</option></select></label>
              <label>Pixel do mapa (m)<input name="pixel_size_m" type="number" min="5" max="50" step="1" defaultValue="10" /></label>
            </div>
            <div className="row3">
              <label>Filtro global (%)<input name="global_limit_pct" type="number" min="1" max="100" defaultValue="50" /></label>
              <label>Raio espacial (m)<input name="local_radius_m" type="number" min="5" max="100" defaultValue="25" /></label>
              <label>Variação local (%)<input name="local_limit_pct" type="number" min="1" max="100" defaultValue="25" /></label>
            </div>
            <div className="hint"><b>Projeção:</b> os arquivos podem estar em WGS 84 ou em outro CRS reconhecido. O processamento é convertido para EPSG:31981.</div>
            <button className="primary" disabled={loading}>{loading?'Processando…':'Gerar mapa de produtividade'}</button>
            {loading && <div className="progress"><div/></div>}
            {error && <div className="error">{error}</div>}
          </form>
        </section>
        <section className="card"><h2>2. Resultado</h2>
          {!result && <div className="hint">Após o processamento, a prévia do mapa, as estatísticas e o arquivo para download aparecerão aqui.</div>}
          {result && s && <>
            <img className="preview" src={`${api}${result.preview_url}`} alt="Mapa de produtividade" />
            <div className="stats">
              <div className="stat">Pontos recortados<b>{s.clipped_points.toLocaleString('pt-BR')}</b></div>
              <div className="stat">Pontos mantidos<b>{s.kept_points.toLocaleString('pt-BR')}</b></div>
              <div className="stat">Removidos<b>{s.removal_pct.toFixed(1)}%</b></div>
              <div className="stat">Média<b>{s.mean.toFixed(2)} {s.unit}</b></div>
              <div className="stat">Mínimo<b>{s.min.toFixed(2)}</b></div>
              <div className="stat">Máximo<b>{s.max.toFixed(2)}</b></div>
            </div>
            <p><small>Krigagem: {s.variogram_model} · Pixel: {s.pixel_size_m} m · CRS: {s.crs}</small></p>
            <a className="secondary" href={`${api}${result.download_url}`}>Baixar resultados completos</a>
          </>}
        </section>
      </div>
    </main>
  </>;
}
