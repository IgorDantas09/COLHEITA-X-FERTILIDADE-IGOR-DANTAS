from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = landscape(A4)
GREEN = colors.HexColor('#145c3a')
DARK_GREEN = colors.HexColor('#0c4028')
SOFT_GREEN = colors.HexColor('#eef5f0')
LIGHT_LINE = colors.HexColor('#d9e4dc')
TEXT = colors.HexColor('#17231c')
MUTED = colors.HexColor('#637168')


def _safe(value: object, fallback: str = 'Não informado') -> str:
    text = str(value or '').strip()
    return text if text else fallback


def _date_br(value: str) -> str:
    value = (value or '').strip()
    parts = value.split('-')
    if len(parts) == 3 and all(parts):
        return f'{parts[2]}/{parts[1]}/{parts[0]}'
    return _safe(value)


def _draw_fitted_image(c: canvas.Canvas, path: Path, x: float, y: float, w: float, h: float) -> None:
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    scale = min(w / iw, h / ih)
    dw = iw * scale
    dh = ih * scale
    dx = x + (w - dw) / 2
    dy = y + (h - dh) / 2
    c.drawImage(image, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')


def _label_value(c: canvas.Canvas, label: str, value: str, x: float, y: float, width: float) -> float:
    c.setFillColor(MUTED)
    c.setFont('Helvetica-Bold', 6.7)
    c.drawString(x, y, label.upper())
    c.setFillColor(TEXT)
    c.setFont('Helvetica-Bold', 8.2)
    shown = value
    while c.stringWidth(shown, 'Helvetica-Bold', 8.2) > width and len(shown) > 5:
        shown = shown[:-2] + '...'
    c.drawString(x, y - 10, shown)
    c.setStrokeColor(LIGHT_LINE)
    c.line(x, y - 15, x + width, y - 15)
    return y - 25


def create_yield_pdf(output_dir: Path, summary: dict, metadata: dict) -> Path:
    """Cria uma página A4 horizontal pronta para impressão e apresentação."""
    pdf_path = output_dir / 'relatorio_mapa_produtividade.pdf'
    map_path = output_dir / 'mapa_produtividade.png'
    c = canvas.Canvas(str(pdf_path), pagesize=landscape(A4))
    c.setTitle('Relatório de Mapa de Produtividade')

    margin = 28
    content_w = PAGE_W - 2 * margin
    top = PAGE_H - margin

    # Cabeçalho
    c.setFillColor(DARK_GREEN)
    c.roundRect(margin, top - 54, content_w, 54, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 18)
    crop_title = 'Mapa de Produtividade de Algodão' if summary.get('unit') == '@/ha' else 'Mapa de Produtividade de Grãos'
    c.drawString(margin + 18, top - 23, crop_title)
    c.setFont('Helvetica', 9)
    subtitle = f"{_safe(metadata.get('fazenda'))} | Talhão {_safe(metadata.get('talhao'))}"
    c.drawString(margin + 18, top - 40, subtitle)
    c.setFont('Helvetica-Bold', 12)
    mean_text = f"Média: {summary['mean']:.2f} {summary['unit']}"
    c.drawRightString(PAGE_W - margin - 18, top - 31, mean_text)

    # Área principal: mapa + painel de identificação
    body_top = top - 68
    body_bottom = 110
    body_h = body_top - body_bottom
    info_w = 178
    gap = 16
    map_x = margin
    map_y = body_bottom
    map_w = content_w - info_w - gap
    map_h = body_h

    c.setFillColor(colors.HexColor('#fbfcfb'))
    c.setStrokeColor(LIGHT_LINE)
    c.roundRect(map_x, map_y, map_w, map_h, 8, stroke=1, fill=1)
    # Margem interna generosa para evitar que o mapa fique colado à moldura.
    _draw_fitted_image(c, map_path, map_x + 18, map_y + 14, map_w - 36, map_h - 28)

    panel_x = map_x + map_w + gap
    c.setFillColor(colors.HexColor('#f7faf8'))
    c.setStrokeColor(LIGHT_LINE)
    c.roundRect(panel_x, map_y, info_w, map_h, 8, stroke=1, fill=1)
    c.setFillColor(GREEN)
    c.setFont('Helvetica-Bold', 11)
    c.drawString(panel_x + 14, body_top - 22, 'IDENTIFICAÇÃO')
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.5)
    c.line(panel_x + 14, body_top - 29, panel_x + info_w - 14, body_top - 29)

    yy = body_top - 48
    item_w = info_w - 28
    yy = _label_value(c, 'Unidade', _safe(metadata.get('unidade')), panel_x + 14, yy, item_w)
    yy = _label_value(c, 'Fazenda', _safe(metadata.get('fazenda')), panel_x + 14, yy, item_w)
    yy = _label_value(c, 'Talhão', _safe(metadata.get('talhao')), panel_x + 14, yy, item_w)
    yy = _label_value(c, 'Data de plantio', _date_br(metadata.get('data_plantio', '')), panel_x + 14, yy, item_w)
    yy = _label_value(c, 'Variedade', _safe(metadata.get('variedade')), panel_x + 14, yy, item_w)
    yy = _label_value(c, 'Sistema', 'SIRGAS 2000 / UTM 21S', panel_x + 14, yy, item_w)
    yy = _label_value(c, 'EPSG', '31981', panel_x + 14, yy, item_w)

    # Resumo técnico inferior
    stats_y = 60
    stats_h = 38
    stats = [
        ('Pontos recortados', f"{summary['clipped_points']:,}".replace(',', '.')),
        ('Pontos mantidos', f"{summary['kept_points']:,}".replace(',', '.')),
        ('Pontos removidos', f"{summary['removed_points']:,}".replace(',', '.')),
        ('Remoção', f"{summary['removal_pct']:.1f}%".replace('.', ',')),
        ('Mínimo', f"{summary['min']:.2f}".replace('.', ',')),
        ('Máximo', f"{summary['max']:.2f}".replace('.', ',')),
    ]
    box_gap = 8
    box_w = (content_w - box_gap * (len(stats) - 1)) / len(stats)
    for index, (label, value) in enumerate(stats):
        x = margin + index * (box_w + box_gap)
        c.setFillColor(SOFT_GREEN)
        c.setStrokeColor(LIGHT_LINE)
        c.roundRect(x, stats_y, box_w, stats_h, 6, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont('Helvetica', 6.8)
        c.drawString(x + 9, stats_y + 24, label)
        c.setFillColor(TEXT)
        c.setFont('Helvetica-Bold', 11)
        c.drawString(x + 9, stats_y + 9, value)

    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.2)
    footer = (
        f"Krigagem: {summary['variogram_model']}   |   Pixel: {summary['pixel_size_m']} m   |   "
        f"Campo: {summary['field']}   |   CRS: {summary['crs']}"
    )
    c.drawString(margin, 40, footer)
    c.drawRightString(PAGE_W - margin, 40, 'Relatório gerado automaticamente')

    c.showPage()
    c.save()
    return pdf_path
