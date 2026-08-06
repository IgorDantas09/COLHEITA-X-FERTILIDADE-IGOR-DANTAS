# Como publicar a Versão 2.3

1. Extraia o ZIP.
2. Envie para o GitHub todo o conteúdo interno da pasta extraída.
3. Faça o commit na branch `main` com a mensagem:
   `Versão 2.3 - relatório PDF e identificação`
4. Aguarde os deploys automáticos do Vercel e do Render.
5. No Render, confirme:
   - Root Directory vazio;
   - Dockerfile Path `services/geo-worker/Dockerfile`;
   - Docker Build Context Directory `.`.
6. Teste a API em `/health`. A versão esperada é `2.3.0-report-pdf`.
7. Processe novamente os shapefiles. Resultados antigos não recebem o novo PDF.
