# Colheita × Fertilidade — Versão 2.2

Versão otimizada para processamento de mapas de produtividade com baixo consumo de memória.

## Alterações da versão 2.2

- painel de resultados posicionado abaixo do formulário;
- apresentação inspirada em folha A4 horizontal;
- mapa ampliado e centralizado;
- retirada da caixa de texto que ficava sobre o mapa;
- estatísticas apresentadas fora da imagem;
- resumo técnico separado do mapa;
- manutenção do pipeline de baixo consumo de memória da versão 2.1.

## Estrutura

- `apps/web`: interface Next.js para o Vercel;
- `services/geo-worker`: API FastAPI em Docker para o Render;
- `libs/agrogeo`: processamento geoespacial, limpeza e krigagem.
