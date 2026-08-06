# Colheita × Fertilidade - Versão 2.3

Aplicação web para limpeza, krigagem e geração de mapa de produtividade agrícola.

## Novidades da versão 2.3

- mapa centralizado, com margem espacial em relação aos eixos;
- prévia organizada como folha A4 horizontal;
- campos de identificação: Unidade, Fazenda, Talhão, Data de plantio e Variedade;
- painel lateral de identificação no relatório;
- geração de relatório PDF A4 horizontal;
- download separado do PDF e dos arquivos técnicos em ZIP;
- manutenção das otimizações de memória da versão 2.1.

## Estrutura

- `apps/web`: frontend Next.js publicado no Vercel;
- `services/geo-worker`: API FastAPI publicada no Render;
- `libs/agrogeo`: limpeza, krigagem, mapa e relatório PDF.

## Render

- Root Directory: vazio
- Dockerfile Path: `services/geo-worker/Dockerfile`
- Docker Build Context Directory: `.`

## Vercel

- Root Directory: `apps/web`
- Variável: `NEXT_PUBLIC_API_URL=https://colheita-x-fertilidade-igor-dantas.onrender.com`
