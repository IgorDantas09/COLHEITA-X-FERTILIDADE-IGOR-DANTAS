# Colheita × Fertilidade — Versão 1

Primeira entrega do sistema de processamento de mapas de produtividade.

## O que esta versão faz

- Upload dos componentes do shapefile ou de um ZIP;
- Upload da colheita e do limite do talhão;
- Leitura do campo de produtividade escolhido pelo usuário;
- Reprojeção automática para **SIRGAS 2000 / UTM zona 21S — EPSG:31981**;
- Conversão de toneladas por hectare para:
  - **arrobas por hectare** quando selecionado `Pluma`;
  - **sacas por hectare** quando selecionado `Grão`;
- Filtro global, padrão de 50%;
- Filtro espacial, padrão de 25 m e 25%;
- Krigagem ordinária local;
- Raster de 10 × 10 m recortado pelo limite do talhão;
- Prévia do primeiro mapa de produtividade;
- Download de ZIP contendo mapa PNG, GeoTIFF, GeoPackage e resumo JSON.

## Arquitetura

- `apps/web`: interface Next.js, publicada no Vercel;
- `services/geo-worker`: API FastAPI com geoprocessamento pesado;
- `libs/agrogeo`: biblioteca Python de filtros, krigagem e mapas.

> O frontend funciona no Vercel. O worker Python deve ser publicado em um serviço de contêiner, como Render, Railway ou Google Cloud Run. A URL desse serviço é informada no Vercel pela variável `NEXT_PUBLIC_API_URL`.

## Rodar no computador

Requer Docker Desktop.

```bash
docker compose up --build
```

Abra:

- Site: http://localhost:3000
- API: http://localhost:8000/docs

## Publicação

Consulte [docs/PUBLICAR_GITHUB_VERCEL.md](docs/PUBLICAR_GITHUB_VERCEL.md).

## Observação sobre a limpeza

O algoritmo segue o procedimento descrito para o Map Filter: remoção global e comparação espacial com vizinhos. Nesta primeira versão, a vizinhança é limitada aos 32 pontos mais próximos dentro do raio definido para manter o processamento viável com centenas de milhares de registros. A calibração fina será feita comparando o resultado com a camada `MAP FILTER` fornecida.
