# Colheita × Fertilidade — Versão 3.0

Inclui toda a fase de colheita e a nova fase de fertilidade após o mapa de produtividade estar pronto.

## Fertilidade
- Upload Excel com Latitude e Longitude;
- leitura e seleção dos atributos;
- conversão K para ppm e Ca/Mg para cmolc/dm³;
- IDW potência 3, pixel 10 m;
- recorte pelo limite do talhão;
- pontos e rótulos das amostras;
- buffer de 50 m e produtividade média;
- Pearson, Spearman e R²;
- PDF A4 horizontal com capa, colheita e uma página por atributo;
- processamento temporário.

## Versão 3.2 — mapa de colheita por ponto e novas classes

- Cada página de nutriente apresenta também um mapa menor da colheita.
- O mapa de colheita reutiliza o raster já processado, sem executar nova interpolação.
- Em cada ponto de coleta é exibida a produtividade média calculada no raio configurado, por padrão 50 m.
- O gráfico de dispersão permanece ao lado do mapa do nutriente.
- Novas classes padrão:
  - K (ppm): < 50; 50–75; 75–100; 100–125; > 125.
  - Ca (cmolc/dm³): < 1,5; 1,5–2,5; 2,5–3,5; 3,5–4,5; > 4,5.
  - Mg (cmolc/dm³): < 0,5; 0,5–1,0; 1,0–1,5; 1,5–2,0; > 2,0.
  - S (mg/dm³): < 10; 10–15; 15–20; 20–25; > 25.
  - B (mg/dm³): < 0,6; 0,6–0,9; 0,9–1,2; 1,2–1,5; > 1,5.
