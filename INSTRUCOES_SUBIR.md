# Como publicar a Versão 3.0
1. Extraia o ZIP.
2. Envie todo o conteúdo interno para a raiz do GitHub.
3. Commit: `Versão 3.0 - módulo de fertilidade`.
4. Aguarde Vercel e Render.
5. Render: Root Directory vazio; Dockerfile `services/geo-worker/Dockerfile`; contexto `.`.
6. Teste `/health`; a versão deve ser `3.0.0-fertility`.
7. Gere primeiro a colheita; depois use a seção **Adicionar análise de fertilidade**.
