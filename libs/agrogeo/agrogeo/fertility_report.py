from __future__ import annotations
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import json

PAGE_W,PAGE_H=landscape(A4)
GREEN=colors.HexColor('#145c3a'); DARK=colors.HexColor('#0c4028'); LINE=colors.HexColor('#d9e4dc'); TEXT=colors.HexColor('#17231c'); MUTED=colors.HexColor('#637168')

def _fit(c,path,x,y,w,h):
    im=ImageReader(str(path)); iw,ih=im.getSize(); s=min(w/iw,h/ih); dw,dh=iw*s,ih*s
    c.drawImage(im,x+(w-dw)/2,y+(h-dh)/2,width=dw,height=dh,preserveAspectRatio=True,mask='auto')

def create_fertility_pdf(yield_output: Path, fertility_output: Path, metadata: dict, fertility_summary: dict) -> Path:
    path=fertility_output/'relatorio_colheita_fertilidade.pdf'; c=canvas.Canvas(str(path),pagesize=landscape(A4)); c.setTitle('Relatório de Colheita e Fertilidade')
    # capa
    c.setFillColor(DARK); c.rect(0,0,PAGE_W,PAGE_H,stroke=0,fill=1); c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold',26); c.drawString(52,PAGE_H-120,'Relatório de Colheita e Fertilidade')
    c.setFont('Helvetica',13); c.drawString(52,PAGE_H-150,f"{metadata.get('fazenda') or 'Fazenda não informada'} | Talhão {metadata.get('talhao') or 'não informado'}")
    c.setFont('Helvetica',10); c.drawString(52,70,'Mapas processados em SIRGAS 2000 / UTM zona 21S — EPSG:31981')
    c.showPage()
    # página de colheita reaproveitando PNG
    c.setFillColor(DARK); c.roundRect(28,PAGE_H-82,PAGE_W-56,54,8,stroke=0,fill=1); c.setFillColor(colors.white); c.setFont('Helvetica-Bold',18); c.drawString(46,PAGE_H-55,'Mapa de Produtividade')
    _fit(c,yield_output/'mapa_produtividade.png',32,65,PAGE_W-64,PAGE_H-165); c.showPage()
    for item in fertility_summary['attributes']:
        slug=item['slug']; attr=item['attribute']
        c.setFillColor(DARK); c.roundRect(28,PAGE_H-75,PAGE_W-56,47,8,stroke=0,fill=1); c.setFillColor(colors.white); c.setFont('Helvetica-Bold',16); c.drawString(44,PAGE_H-51,f'Fertilidade × Produtividade — {attr}')
        map_x,map_y,map_w,map_h=28,108,430,420
        c.setStrokeColor(LINE); c.roundRect(map_x,map_y,map_w,map_h,7,stroke=1,fill=0)
        _fit(c,fertility_output/item['map_url'],map_x+8,map_y+8,map_w-16,map_h-16)

        panel_x=472; panel_w=PAGE_W-panel_x-28
        top_h=205; bottom_h=198
        c.setStrokeColor(LINE); c.roundRect(panel_x,map_y+map_h-top_h,panel_w,top_h,7,stroke=1,fill=0)
        _fit(c,fertility_output/item['yield_map_url'],panel_x+6,map_y+map_h-top_h+6,panel_w-12,top_h-12)
        c.setStrokeColor(LINE); c.roundRect(panel_x,map_y,panel_w,bottom_h,7,stroke=1,fill=0)
        _fit(c,fertility_output/item['scatter_url'],panel_x+6,map_y+6,panel_w-12,bottom_h-12)

        stats_y=74
        labels=[('Média',item['mean']),('Mínimo',item['min']),('Máximo',item['max']),('Pearson',item['pearson']),('Spearman',item['spearman']),('R²',item['r2'])]
        box_w=(PAGE_W-56-5*8)/6
        for idx,(lab,val) in enumerate(labels):
            bx=28+idx*(box_w+8)
            c.setFillColor(colors.HexColor('#f2f7f3')); c.setStrokeColor(LINE); c.roundRect(bx,stats_y,box_w,27,5,stroke=1,fill=1)
            c.setFillColor(MUTED); c.setFont('Helvetica',6.5); c.drawString(bx+7,stats_y+16,lab.upper())
            c.setFillColor(TEXT); c.setFont('Helvetica-Bold',8.5)
            shown='—' if val is None else f'{val:.3f}'
            c.drawString(bx+7,stats_y+6,shown)
        c.setFillColor(MUTED); c.setFont('Helvetica',7); c.drawString(28,58,f"IDW potência {fertility_summary['idw_power']} | Pixel {fertility_summary['pixel_size_m']} m | Buffer de produtividade {fertility_summary['buffer_radius_m']} m")
        c.showPage()
    c.save(); return path
