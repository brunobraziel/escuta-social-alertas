"""Deterministic, data-driven cards. No network or generative image calls."""
from collections import Counter
import io
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

RED = '#E30613'
ORANGE = '#F28C28'
INK = '#20323D'
BG = '#FFF8F2'
MUTED = '#61717B'
PALETTE = [RED, ORANGE, '#9C1020', '#B35B12', '#F5999E', '#FFC487']
ASSETS = Path(__file__).with_name('assets')


def font(size, bold=False):
    filename = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    candidates = [Path('/usr/share/fonts/truetype/dejavu') / filename,
                  ASSETS / filename]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    # Developer preview on macOS; production installs DejaVu explicitly.
    name = 'Arial Bold.ttf' if bold else 'Arial.ttf'
    return ImageFont.truetype('/System/Library/Fonts/Supplemental/' + name, size)


def plain(text):
    return text.replace('*', '').replace('_', '').strip()


def wrap(draw, text, face, width):
    """Wrap even long unbroken queries; never truncate data."""
    result = []
    for para in text.split('\n'):
        line = ''
        for char in para:
            if line and draw.textlength(line + char, font=face) > width:
                cut = line.rfind(' ')
                if cut > len(line) // 2:
                    result.append(line[:cut]); line = line[cut + 1:]
                else:
                    result.append(line); line = ''
            line += char
        result.append(line.rstrip())
    return result


def text(draw, xy, value, size, width, *, bold=False, color=INK, gap=9):
    x, y = xy
    for line in wrap(draw, value, font(size, bold), width):
        draw.text((x, y), line, font=font(size, bold), fill=color)
        y += size + gap
    return y


def parse_states(full):
    matches = list(re.finditer(r'📍 \*([^\n]+) \(([A-Z]{2})\)\*\n', full))
    cards = []
    for i, m in enumerate(matches):
        block = full[m.end():matches[i+1].start() if i+1 < len(matches) else len(full)]
        topics = []
        for rank, term, move in re.findall(r'(?m)^(\d+)\. \*(.+?)\* ([^\n]+)', block):
            topics.append((int(rank), term, move))
        cards.append({'uf': m[2], 'name': m[1], 'topics': topics})
    if len(cards) != 27 or len({c['uf'] for c in cards}) != 27:
        raise ValueError('State image requires 27 distinct UFs')
    return full[:matches[0].start()].strip(), cards


def parse_related(full):
    matches = list(re.finditer(r'(?m)^\*([^\n]+)\* — ([^\n]+)\nBusca-base: ([^\n]+)\n', full))
    cards = []
    for i, m in enumerate(matches):
        block = full[m.end():matches[i+1].start() if i+1 < len(matches) else len(full)]
        topics = []
        entries = list(re.finditer(r'(?m)^(\d+)\. \*(.+?)\*', block))
        for j, entry in enumerate(entries):
            rest = block[entry.end():entries[j+1].start() if j+1 < len(entries) else len(block)]
            variants = re.search(r'(?m)^   Agrupadas: (.+)$', rest)
            topics.append((int(entry[1]), entry[2], variants[1] if variants else ''))
        if not topics:
            raise ValueError('Related card has no queries')
        cards.append({'theme': m[1], 'area': m[2], 'base': m[3], 'topics': topics})
    if not cards:
        raise ValueError('No related cards')
    return full[:matches[0].start()].strip(), cards


def jpeg(im):
    out = io.BytesIO()
    im.save(out, format='JPEG', quality=94, subsampling=0)
    return out.getvalue()


def state_images(full):
    header, cards = parse_states(full)
    by = {c['uf']: c for c in cards}
    leaders = Counter(c['topics'][0][1].casefold() for c in cards if c['topics'])
    colors = {term: PALETTE[i % len(PALETTE)] for i, (term, _) in enumerate(leaders.most_common())}
    w = 3600
    probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    # Same layout as approved preview, variable card heights for longer terms.
    def card_height(c, cw):
        return 110 + sum(max(50, max(len(wrap(probe, t, font(28, True), cw-235))*37, len(wrap(probe, m.replace('(','').replace(')',''), font(22), 150))*31)+12) for _, t, m in c['topics'])
    left = ['RR','AP','AM','PA','AC','RO','TO','MT','MS']
    right = ['MA','PI','CE','RN','PB','PE','AL','SE','BA']
    bottom = ['GO','DF','MG','ES','RJ','SP','PR','SC','RS']
    side_h = max(345, *(card_height(c, 825) for c in cards))
    bottom_h = max(410, *(card_height(by[u], 544) for u in bottom))
    h = max(280+9*(side_h+20), 2200+3*(bottom_h+20)) + 310
    im = Image.new('RGB', (w, h), BG); d = ImageDraw.Draw(im)
    d.rectangle((0,0,w,230), fill='#990B16')
    d.text((65,35), 'BRASIL • TOP 5 POR ESTADO', font=font(75,True), fill='white')
    stamp = re.search(r'\*Dados coletados:\* ([^\n]+)', header)
    label = ('TESTE • ' if full.startswith('*TESTE*') else '') + 'Coleta: ' + (stamp[1] if stamp else 'conforme legenda')
    d.text((65,145), label, font=font(34), fill='white')
    def project(lon,lat): return (990+(lon+74)*40, 330+(6-lat)*40)
    shapes = json.loads((ASSETS/'br-states.json').read_text())
    centers = {}
    for uf, polygons in shapes.items():
        c = by[uf]; color = colors.get(c['topics'][0][1].casefold(), '#DDD') if c['topics'] else '#DDD'
        biggest = max(polygons, key=len)
        pts = [project(*p) for p in biggest]
        a = sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))
        centers[uf] = tuple(sum((pts[i][k]+pts[(i+1)%len(pts)][k])*(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1]) for i in range(len(pts)))/(3*a) for k in (0,1))
        for polygon in polygons:
            p = [project(*v) for v in polygon]
            d.polygon(p, fill=color); d.line(p+[p[0]], fill='white', width=4)
    offsets = {'DF':(65,-12),'RN':(105,-30),'PB':(145,5),'PE':(155,35),'AL':(140,50),'SE':(130,80),'ES':(100,0),'RJ':(100,45)}
    for uf, (x,y) in centers.items():
        if uf in offsets:
            dx,dy=offsets[uf]; xx,yy=x+dx,y+dy
            d.line((x,y,xx,yy), fill=INK,width=2)
            d.rounded_rectangle((xx-33,yy-24,xx+33,yy+24),radius=7,fill='white')
            d.text((xx,yy),uf,font=font(27,True),fill=INK,anchor='mm')
        else:
            d.text((x,y),uf,font=font(32,True),fill='white',anchor='mm',stroke_width=1,stroke_fill='#71353B')
    d.text((1060,1880),'COR DO MAPA = TERMO EM 1º LUGAR',font=font(31,True),fill=INK)
    # Detailed leader labels live in each UF card; cap legend footprint only.
    for i,(term,count) in enumerate(leaders.most_common(4)):
        y=1935+i*53
        d.rounded_rectangle((1060,y,1092,y+32),radius=6,fill=colors[term])
        text(d,(1110,y-3),f'{term} • {count} UFs',26,1420)
    def card(uf,x,y,cw,ch):
        c=by[uf]
        d.rounded_rectangle((x,y,x+cw,y+ch),radius=22,fill='white',outline='#F0D9CA',width=2)
        color=colors.get(c['topics'][0][1].casefold(),RED) if c['topics'] else RED
        d.rounded_rectangle((x+18,y+18,x+90,y+67),radius=9,fill=color)
        d.text((x+54,y+42),uf,font=font(28,True),fill='white',anchor='mm')
        text(d,(x+104,y+26),c['name'],29 if cw>700 else 23,cw-120,bold=True)
        yy=y+95
        if not c['topics']: text(d,(x+22,yy),'Sem índice válido neste lote.',26,cw-44)
        for rank,term,move in c['topics']:
            d.text((x+22,yy),str(rank),font=font(26),fill=MUTED)
            end=text(d,(x+60,yy),term,28,cw-235,bold=True)
            color='#177660' if move.startswith('↑') else '#B44955' if move.startswith('↓') else MUTED
            # Wrap long zero/base labels in their own right column.
            e2=text(d,(x+cw-166,yy),move.replace('(','').replace(')',''),22,150,color=color)
            yy=max(end,e2)+12
    for i,uf in enumerate(left):card(uf,55,280+i*(side_h+20),825,side_h)
    for i,uf in enumerate(right):card(uf,2720,280+i*(side_h+20),825,side_h)
    for i,uf in enumerate(bottom):card(uf,945+(i%3)*568,2200+(i//3)*(bottom_h+20),544,bottom_h)
    y=h-240
    text(d,(70,y),'↑ Subiu   ↓ Caiu   → Estável • Variação do índice relativo, não de buscas absolutas.',34,w-140)
    text(d,(70,y+70),'Ranking entre termos monitorados. Comparação, resumo e leitura de IA na legenda.',32,w-140,color=MUTED)
    text(d,(70,y+135),'Texto completo no privado: use a reação de acessibilidade abaixo da imagem.',32,w-140,color=MUTED)
    return [jpeg(im)], header


def related_images(full):
    header,cards=parse_related(full)
    w=1800; margin=55; inner=w-2*margin
    probe=ImageDraw.Draw(Image.new('RGB',(1,1)))
    def height(c):
        y=135
        for _,term,variants in c['topics']:
            y+=len(wrap(probe,term,font(35,True),inner-150))*44+22
            if variants:y+=len(wrap(probe,'Agrupadas: '+variants,font(29),inner-150))*38+35
        return y+25
    # A single image whenever legible; paginate busy lots rather than clip topics.
    pages=[]; current=[]; used=360
    for c in cards:
        hh=height(c)
        if hh>6500: raise ValueError('Related card exceeds readable image size')
        if current and used+hh>7400:pages.append(current);current=[];used=360
        current.append(c);used+=hh+28
    if current:pages.append(current)
    results=[]
    for page_n,page in enumerate(pages,1):
        h=360+sum(height(c)+28 for c in page)+280
        im=Image.new('RGB',(w,h),BG); d=ImageDraw.Draw(im)
        d.rounded_rectangle((margin,35,w-margin,205),radius=28,fill=RED)
        d.text((w//2,90),'CONSULTAS RELACIONADAS',font=font(62,True),fill='white',anchor='mm')
        stamp=re.search(r'\*Dados atualizados:\* ([^\n]+)',header)
        label=('TESTE • ' if full.startswith('*TESTE*') else '') + (stamp[1] if stamp else 'Brasil')
        if len(pages)>1:label+=f' • Parte {page_n}/{len(pages)}'
        d.text((w//2,163),label,font=font(30),fill='white',anchor='mm')
        text(d,(margin+15,245),'Até 4 grupos por busca-base • Consultas em alta primeiro',34,inner-30,bold=True)
        y=340
        for c in page:
            hh=height(c)
            d.rounded_rectangle((margin,y,w-margin,y+hh),radius=25,fill='white',outline='#F0D9CA',width=2)
            d.rounded_rectangle((margin,y,w-margin,y+108),radius=25,fill=RED)
            text(d,(margin+25,y+14),c['theme']+' • '+c['area'],29,inner-50,bold=True,color='white')
            text(d,(margin+25,y+56),'Busca-base: '+c['base'],32,inner-50,bold=True,color='white')
            yy=y+135
            for rank,term,variants in c['topics']:
                d.ellipse((margin+24,yy,margin+83,yy+59),fill=ORANGE)
                d.text((margin+53,yy+28),str(rank),font=font(33,True),fill='white',anchor='mm')
                yy=text(d,(margin+105,yy),term,35,inner-150,bold=True)+20
                if variants:
                    lines=wrap(d,'Agrupadas: '+variants,font(29),inner-150); bh=len(lines)*38+26
                    d.rounded_rectangle((margin+100,yy,w-margin-25,yy+bh),radius=17,fill='#FFF0E0')
                    yy=text(d,(margin+115,yy+12),'Agrupadas: '+variants,29,inner-150,color='#783C17')+25
            y+=hh+28
        text(d,(margin+20,y+20),'Consultas no buscador não são afirmações verificadas. Não indicam apoio ou rejeição.',31,inner-40)
        text(d,(margin+20,y+110),'Fonte: Google Trends • Variantes visíveis; posições e índices não são somados.',28,inner-40,color=MUTED)
        text(d,(margin+20,y+185),'Texto no privado: use a reação de acessibilidade abaixo da imagem.',28,inner-40,color=MUTED)
        results.append(jpeg(im))
    return results,header


def render_images(kind, full):
    if kind=='states':return state_images(full)
    if kind=='related':return related_images(full)
    raise ValueError('Unknown presentation')
