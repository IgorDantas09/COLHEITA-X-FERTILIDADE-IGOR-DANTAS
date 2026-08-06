# Como publicar

## 1. Enviar os arquivos ao GitHub

1. Extraia o ZIP recebido do ChatGPT.
2. Abra seu repositório no GitHub.
3. Clique em **Add file → Upload files**.
4. Arraste **o conteúdo de dentro da pasta** `colheita-x-fertilidade-v1`, não a pasta ZIP.
5. Aguarde todos os arquivos carregarem.
6. Em **Commit changes**, escreva `Primeira versão do mapa de colheita`.
7. Clique em **Commit changes**.

Para projetos com muitos arquivos, o método mais confiável é GitHub Desktop:

1. Instale o GitHub Desktop.
2. Clone o repositório.
3. Copie o conteúdo desta pasta para dentro da pasta clonada.
4. Faça o commit e clique em **Push origin**.

## 2. Publicar o worker Python

O worker não deve ser publicado como função comum do Vercel, porque usa GeoPandas, Rasterio, SciPy e processamento de krigagem.

### Render

1. Crie um **Web Service** ligado ao mesmo repositório.
2. Escolha ambiente **Docker**.
3. Em Dockerfile Path, informe:
   `services/geo-worker/Dockerfile`
4. Em Docker Build Context, use a raiz do repositório: `.`
5. Adicione a variável:
   `ALLOWED_ORIGINS=https://SEU-SITE.vercel.app`
6. Publique e copie a URL, por exemplo:
   `https://seu-worker.onrender.com`

## 3. Publicar o frontend no Vercel

1. No Vercel, clique em **Add New → Project**.
2. Importe o repositório.
3. Em **Root Directory**, escolha `apps/web`.
4. Adicione a variável:
   `NEXT_PUBLIC_API_URL=https://seu-worker.onrender.com`
5. Clique em **Deploy**.
6. Volte ao Render e atualize `ALLOWED_ORIGINS` com a URL final do Vercel.

## Limites iniciais recomendados

- Colheita: até 500 mil pontos;
- Pixel: 10 m;
- Vizinhos da krigagem: 24;
- Tempo de processamento esperado: depende do servidor e da quantidade de dados;
- Arquivos são temporários e expiram automaticamente.
