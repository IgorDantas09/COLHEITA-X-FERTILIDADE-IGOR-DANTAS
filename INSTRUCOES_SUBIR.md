# Versão 3.1 — correção das classes de fertilidade

1. Substitua todo o conteúdo do repositório pelo conteúdo desta pasta.
2. Commit: `Versão 3.1 - corrigir legendas da fertilidade`.
3. Aguarde Vercel e Render concluírem os deploys.
4. Verifique `/health`; a versão deve ser `3.1.0-fertility-bins-fix`.
5. Processe novamente a colheita e depois a fertilidade.

A correção impede o erro `bins must be monotonically increasing or decreasing` quando os valores do talhão estão todos acima ou abaixo das faixas agronômicas padrão.
