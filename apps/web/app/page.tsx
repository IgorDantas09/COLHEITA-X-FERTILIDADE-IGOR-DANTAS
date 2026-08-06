'use client';

import { FormEvent, useState } from 'react';

type Result = {
  job_id: string;
  summary: {
    original_points: number;
    clipped_points: number;
    kept_points: number;
    removed_points: number;
    removal_pct: number;
    mean: number;
    median: number;
    min: number;
    max: number;
    unit: string;
    crs: string;
    field: string;
    variogram_model: string;
    pixel_size_m: number;
  };
  preview_url: string;
  download_url: string;
};

function formatNumber(value: number, decimals = 0) {
  return value.toLocaleString('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export default function Page() {
  const api = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Result | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const formData = new FormData(event.currentTarget);
      const response = await fetch(`${api}/process-yield`, {
        method: 'POST',
        body: formData,
      });
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json')
        ? await response.json()
        : { detail: await response.text() };

      if (!response.ok) {
        throw new Error(data.detail || 'Não foi possível processar os arquivos.');
      }
      setResult(data);
      window.setTimeout(() => {
        document.getElementById('resultado')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 120);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro inesperado.');
    } finally {
      setLoading(false);
    }
  }

  const summary = result?.summary;

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <div className="brand">Colheita × Fertilidade</div>
          <div className="badge">Versão 2.2 · Layout A4 horizontal</div>
        </div>
      </header>

      <main>
        <section className="hero">
          <h1>Processamento do mapa de colheita</h1>
          <p>
            Envie os dados de colheita e o limite do talhão. O sistema limpa os pontos,
            executa a krigagem e gera o mapa de produtividade.
          </p>
        </section>

        <section className="card input-card">
          <h2>1. Arquivos e parâmetros</h2>
          <form className="form" onSubmit={submit}>
            <div className="upload-grid">
              <label>
                Limite do talhão
                <input
                  required
                  name="boundary_files"
                  type="file"
                  multiple
                  accept=".zip,.shp,.shx,.dbf,.prj,.cpg"
                />
                <small>Selecione um ZIP ou, juntos, os arquivos SHP, SHX, DBF e PRJ.</small>
              </label>

              <label>
                Dados de colheita
                <input
                  required
                  name="harvest_files"
                  type="file"
                  multiple
                  accept=".zip,.shp,.shx,.dbf,.prj,.cpg"
                />
                <small>O shapefile deve ser uma camada de pontos.</small>
              </label>
            </div>

            <div className="row">
              <label>
                Campo de produtividade
                <input name="value_field" defaultValue="VRYIELDMAS" />
              </label>
              <label>
                Tipo de colheita
                <select name="harvest_type" defaultValue="pluma">
                  <option value="pluma">Pluma de algodão (@/ha)</option>
                  <option value="grao">Grão (sc/ha)</option>
                </select>
              </label>
            </div>

            <div className="row">
              <label>
                Unidade original
                <select name="source_unit" defaultValue="t_ha">
                  <option value="t_ha">Toneladas/hectare</option>
                  <option value="kg_ha">Quilogramas/hectare</option>
                  <option value="arroba_ha">Arrobas/hectare</option>
                  <option value="sc_ha">Sacas/hectare</option>
                </select>
              </label>
              <label>
                Pixel do mapa (m)
                <input name="pixel_size_m" type="number" min="5" max="50" step="1" defaultValue="10" />
              </label>
            </div>

            <div className="row3">
              <label>
                Filtro global (%)
                <input name="global_limit_pct" type="number" min="1" max="100" defaultValue="50" />
              </label>
              <label>
                Raio espacial (m)
                <input name="local_radius_m" type="number" min="5" max="100" defaultValue="25" />
              </label>
              <label>
                Variação local (%)
                <input name="local_limit_pct" type="number" min="1" max="100" defaultValue="25" />
              </label>
            </div>

            <div className="hint">
              <b>Projeção:</b> arquivos em outro CRS reconhecido são convertidos para SIRGAS 2000 /
              UTM zona 21S — EPSG:31981. Arquivos que já estejam nesse CRS são mantidos sem reprojeção.
            </div>

            <button className="primary" disabled={loading}>
              {loading ? 'Processando…' : 'Gerar mapa de produtividade'}
            </button>
            {loading && (
              <div className="progress" aria-label="Processamento em andamento">
                <div />
              </div>
            )}
            {error && <div className="error">{error}</div>}
          </form>
        </section>

        <section id="resultado" className="card result-card">
          <h2>2. Resultado</h2>

          {!result && (
            <div className="hint">
              Após o processamento, o mapa, as estatísticas e o arquivo para download aparecerão aqui.
            </div>
          )}

          {result && summary && (
            <div className="a4-sheet">
              <div className="report-heading">
                <div>
                  <span className="eyebrow">MAPA DE PRODUTIVIDADE</span>
                  <h3>Resultado do processamento</h3>
                </div>
                <div className="mean-highlight">
                  <span>Média</span>
                  <strong>{formatNumber(summary.mean, 2)} {summary.unit}</strong>
                </div>
              </div>

              <div className="map-frame">
                <img
                  className="preview"
                  src={`${api}${result.preview_url}`}
                  alt="Mapa interpolado de produtividade"
                />
              </div>

              <div className="stats stats-six">
                <div className="stat"><span>Pontos recortados</span><b>{formatNumber(summary.clipped_points)}</b></div>
                <div className="stat"><span>Pontos mantidos</span><b>{formatNumber(summary.kept_points)}</b></div>
                <div className="stat"><span>Pontos removidos</span><b>{formatNumber(summary.removed_points)}</b></div>
                <div className="stat"><span>Remoção</span><b>{formatNumber(summary.removal_pct, 1)}%</b></div>
                <div className="stat"><span>Mínimo</span><b>{formatNumber(summary.min, 2)}</b></div>
                <div className="stat"><span>Máximo</span><b>{formatNumber(summary.max, 2)}</b></div>
              </div>

              <div className="technical-strip">
                <span><b>Krigagem:</b> {summary.variogram_model}</span>
                <span><b>Pixel:</b> {summary.pixel_size_m} m</span>
                <span><b>Campo:</b> {summary.field}</span>
                <span><b>CRS:</b> {summary.crs}</span>
              </div>

              <a className="secondary" href={`${api}${result.download_url}`}>
                Baixar resultados completos
              </a>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
