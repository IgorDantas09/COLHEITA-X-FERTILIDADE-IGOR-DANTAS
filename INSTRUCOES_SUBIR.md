# Atualização para a versão 3.2

1. Extraia o arquivo ZIP.
2. No GitHub, substitua o conteúdo do repositório pelo conteúdo interno da pasta extraída.
3. Faça o commit diretamente na branch `main` com a mensagem:

   `Versão 3.2 - mapa de colheita por ponto e novas classes`

4. Aguarde os deploys automáticos do Vercel e do Render.
5. Confirme no Render:
   - Root Directory: vazio
   - Dockerfile Path: `services/geo-worker/Dockerfile`
   - Docker Build Context Directory: `.`
6. Abra `/health`. A versão esperada é `3.2.0-fertility-yield-points`.
7. Processe novamente a colheita e a fertilidade para gerar as novas imagens e o novo PDF.
