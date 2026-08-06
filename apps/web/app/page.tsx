'use client';

import { FormEvent, useState } from 'react';

type ReportMetadata = {
  unidade: string;
  fazenda: string;
  talhao: string;
  data_plantio: string;
  variedade: string;
};

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
    report_metadata: ReportMetadata;
  };
  preview_url: string;
  pdf_url: string;
  download_url: string;
};

function formatNumber(value: number, decimals = 0) {
  return value.toLocaleString('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function displayDate(value: string) {
  if (!value) return 'Não informado';
  const [year, month, day] = value.split('-');
  return year && month && day ? `${day}/${month}/${year}` : value;
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
  const metadata = summary?.report_metadata;

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <div className="brand">Colheita × Fertilidade</div>
          <div className="badge">Versão 2.3 · Relatório PDF A4</div>
        </div>
      </header>

      <main>
        <section className="hero">
          <h1>Processamento do mapa de colheita</h1>
          <p>
            Envie os dados de colheita e o limite do talhão. O sistema limpa os pontos,
            executa a krigagem e gera o mapa e o relatório em PDF.
          </p>
        </section>

        <section className="card input-card">
          <h2>1. Identificação, arquivos e parâmetros</h2>
          <form className="form" onSubmit={submit}>
            <fieldset className="metadata-fieldset">
              <legend>Identificação do relatório</legend>
              <div className="metadata-grid">
                <label>
                  Unidade
                  <input name="unidade" placeholder="Ex.: UP Vó Luzia" maxLength={100} />
                </label>
                <label>
                  Fazenda
                  <input name="fazenda" placeholder="Ex.: Fazenda Janba" maxLength={100} />
                </label>
                <label>
                  Talhão
                  <input name="talhao" placeholder="Ex.: 180 JB" maxLength={100} />
                </label>
                <label>
                  Data de plantio
                  <input name="data_plantio" type="date" />
                </label>
                <label>
                  Variedade
                  <input name="variedade" placeholder="Ex.: FM 985 GLTP" maxLength={100} />
                </label>
              </div>
            </fieldset>

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
              Após o processamento, o mapa, as estatísticas e o relatório PDF aparecerão aqui.
            </div>
          )}

          {result && summary && metadata && (
            <div className="a4-sheet">
              <div className="report-heading">
                <div>
                  <span className="eyebrow">MAPA DE PRODUTIVIDADE</span>
                  <h3>{metadata.fazenda || 'Relatório de produtividade'}</h3>
                  <p className="report-subtitle">
                    {metadata.talhao ? `Talhão ${metadata.talhao}` : 'Talhão não informado'}
                  </p>
                </div>
                <div className="mean-highlight">
                  <span>Média de produtividade</span>
                  <strong>{formatNumber(summary.mean, 2)} {summary.unit}</strong>
                </div>
              </div>

              <div className="report-body">
                <div className="map-frame">
                  <img
                    className="preview"
                    src={`${api}${result.preview_url}`}
                    alt="Mapa interpolado de produtividade"
                  />
                </div>

                <aside className="identification-panel">
                  <h4>Identificação</h4>
                  <dl>
                    <div><dt>Unidade</dt><dd>{metadata.unidade || 'Não informado'}</dd></div>
                    <div><dt>Fazenda</dt><dd>{metadata.fazenda || 'Não informado'}</dd></div>
                    <div><dt>Talhão</dt><dd>{metadata.talhao || 'Não informado'}</dd></div>
                    <div><dt>Data de plantio</dt><dd>{displayDate(metadata.data_plantio)}</dd></div>
                    <div><dt>Variedade</dt><dd>{metadata.variedade || 'Não informado'}</dd></div>
                    <div><dt>Sistema</dt><dd>SIRGAS 2000 / UTM 21S</dd></div>
                    <div><dt>EPSG</dt><dd>31981</dd></div>
                  </dl>
                </aside>
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

              <div className="download-actions">
                <a className="secondary pdf-button" href={`${api}${result.pdf_url}`}>
                  Baixar relatório em PDF
                </a>
                <a className="secondary outline-button" href={`${api}${result.download_url}`}>
                  Baixar arquivos técnicos (ZIP)
                </a>
              </div>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
