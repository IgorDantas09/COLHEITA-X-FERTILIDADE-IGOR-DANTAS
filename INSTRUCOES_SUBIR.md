# Como substituir o repositório

1. Extraia este ZIP no computador.
2. Abra a pasta `colheita-x-fertilidade-v2-completa`.
3. No GitHub, clique em **Add file → Upload files**.
4. Arraste **todos os arquivos e pastas que estão dentro da pasta extraída**.
5. Não envie o ZIP fechado para dentro do repositório.
6. Faça o commit na branch `main` com a mensagem:

```text
Versão 2.1 completa - otimização de memória
```

## Depois do commit

### Vercel

O Vercel deve iniciar novo deploy automaticamente. Confirme:

- Root Directory: `apps/web`
- variável `NEXT_PUBLIC_API_URL` preservada.

### Render

O Render também deve iniciar novo deploy. A configuração deve continuar:

- Root Directory: vazio
- Dockerfile Path: `services/geo-worker/Dockerfile`
- Docker Build Context Directory: `.`

Se não iniciar, use **Manual Deploy → Clear build cache & deploy**.

Teste a versão em:

```text
https://SEU-SERVICO.onrender.com/health
```

A resposta deverá indicar `2.1.0-low-memory`.
