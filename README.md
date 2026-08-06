# Colheita × Fertilidade — Versão 2.1

Projeto completo da primeira etapa do sistema para geração de mapas de produtividade agrícola.

## Funcionalidades desta entrega

- Upload do limite do talhão e da colheita por ZIP ou pelos componentes SHP, SHX, DBF, PRJ e CPG;
- seleção entre colheita de **pluma de algodão** e **grãos**;
- seleção do campo de produtividade, com padrão `VRYIELDMAS`;
- conversão de t/ha ou kg/ha para @/ha ou sc/ha;
- reconhecimento do CRS de entrada e reprojeção para **SIRGAS 2000 / UTM zona 21S — EPSG:31981**;
- filtro global e filtro espacial configuráveis;
- ajuste automático do variograma entre modelos esférico, exponencial e gaussiano;
- krigagem ordinária local;
- raster recortado pelo limite do talhão;
- prévia PNG e download de ZIP com GeoTIFF, GeoPackage e JSON.

## Otimizações de memória da Versão 2.1

- leitura somente da geometria e do campo de produtividade;
- filtro espacial executado em blocos;
- agregação espacial antes da krigagem;
- grade limitada para impedir explosão de memória;
- raster em `float32`;
- exportação dos pontos filtrados para GeoPackage em blocos;
- arquivos recebidos gravados diretamente no disco temporário;
- remoção automática dos resultados temporários;
- apenas um processo Uvicorn no backend.

> Mesmo com as otimizações, 512 MB de RAM continuam sendo um limite apertado para arquivos muito grandes. Esta versão evita o principal pico de memória da versão anterior, mas o plano Standard do Render ou outro serviço com 2 GB de RAM é mais adequado para uso profissional.

## Estrutura

```text
apps/web/                 Frontend Next.js para Vercel
services/geo-worker/      API FastAPI/Docker para Render
libs/agrogeo/agrogeo/     Pipeline de geoprocessamento
.github/workflows/        Validação automática
docs/                     Instruções de publicação
```

## Vercel

- Framework: Next.js
- Root Directory: `apps/web`
- Variável:

```text
NEXT_PUBLIC_API_URL=https://SEU-SERVICO.onrender.com
```

## Render

- Language: Docker
- Root Directory: vazio
- Dockerfile Path: `services/geo-worker/Dockerfile`
- Docker Build Context Directory: `.`

A API oferece:

- `GET /`
- `GET /health`
- `POST /process-yield`
- `GET /jobs/{job_id}/preview`
- `GET /jobs/{job_id}/download`

## Desenvolvimento local

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/docs
