# Publicação da Versão 2.1

## 1. GitHub

Extraia o ZIP. No GitHub, use **Add file → Upload files** e envie o conteúdo interno da pasta, não o ZIP fechado.

Mensagem de commit sugerida:

```text
Versão 2.1 completa - otimização de memória
```

## 2. Vercel

Importe o repositório com:

- Application Preset: Next.js
- Root Directory: `apps/web`
- Build/Install/Output: padrões do Next.js

Adicione a variável:

```text
NEXT_PUBLIC_API_URL=https://SEU-SERVICO.onrender.com
```

Depois faça um novo deploy.

## 3. Render

Use estas configurações:

- Language: Docker
- Branch: `main`
- Root Directory: **vazio**
- Dockerfile Path: `services/geo-worker/Dockerfile`
- Docker Build Context Directory: `.`

Não use `services/geo-worker` como Root Directory, pois o Dockerfile também copia a biblioteca `libs/agrogeo`.

Após o deploy, teste:

```text
https://SEU-SERVICO.onrender.com/health
https://SEU-SERVICO.onrender.com/docs
```

## 4. Render já existente

Se o serviço já estiver criado, o commit no GitHub inicia o deploy automaticamente. Caso necessário:

```text
Manual Deploy → Clear build cache & deploy
```
