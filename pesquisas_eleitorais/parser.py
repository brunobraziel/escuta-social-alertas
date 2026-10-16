"""Extração conservadora de tabela explícita de votos totais, sem inferir resultados."""
import re
from core.alerta import normalize

INSTITUTES = (
    "Datafolha", "PoderData", "Quaest", "AtlasIntel", "Ipsos-Ipec", "Ipec",
    "Ipsos", "Paraná Pesquisas", "Real Time Big Data", "Futura", "Veritá",
    "Ipespe", "MDA", "Sensus", "Ibope", "FSB", "Ideia", "Brasmarket",
    "Vox Populi", "Gerp", "Iprev", "Percent Brasil", "100% Cidades",
    "Opinião", "IRG", "Ipeci", "Ipeca", "Intenção", "Ibespe",
    "Strategia", "Exata", "Econométrica", "Amostragem", "Paraná Instituto",
)


def matches_poll(title, description):
    text = normalize(title)
    if any(word in text for word in ("rejei", "aprov", "desaprov", "problemas", "preocupac")):
        return False
    # O catálogo ajuda a reconhecer nomes; não é uma lista de permissão.
    return (("intenc" in text and "voto" in text)
            or ("pesquisa" in text and any(w in text for w in ("presiden", "turno", "voto", "%")))
            or (any(normalize(name) in text for name in INSTITUTES) and any(w in text for w in ("%", "turno", "presiden"))))


def parse_total_poll(article):
    text = article["description"]
    normalized = normalize(text)
    # Este primeiro conector cobre exclusivamente presidente, Brasil, segundo turno.
    if not ("presidente" in article["url"] or "presidencia" in normalized):
        return None
    if not re.search(r"(?:2[ºo°]?|segundo)\s*turno", normalize(article["title"])):
        return None
    marker = re.search(r"(?:veja os numeros\s*[-–:]?\s*)?votos totais\s*:", normalized)
    if not marker:
        return None
    block = text[marker.end():]
    block = re.split(r"Datafolha|Em relação|Em relacao|Saiba mais|Veja também|Veja tambem", block, maxsplit=1, flags=re.I)[0][:1500]
    entries = re.findall(r"([A-ZÀ-Ý][A-Za-zÀ-ÿ .’'-]{1,70})\s*\(([A-Z][A-Z0-9 -]{0,20})\)\s*:\s*(\d{1,3}(?:[,.]\d+)?)\s*%", block)
    if len(entries) < 2:
        return None
    results = [{"candidate": name.strip(), "party": party, "percent": float(value.replace(",", "."))} for name, party, value in entries]
    if len({r["candidate"] for r in results}) != len(results) or any(not 0 <= r["percent"] <= 100 for r in results):
        return None
    others = []
    for pattern, label in [(r"(?:Em )?branco/nulo/nenhum\s*:\s*(\d+(?:[,.]\d+)?)%", "Branco/nulo/nenhum"), (r"Indecisos\s*:\s*(\d+(?:[,.]\d+)?)%", "Indecisos")]:
        match = re.search(pattern, block, flags=re.I)
        if not match:
            return None
        others.append({"label": label, "percent": float(match.group(1).replace(",", "."))})
    # Requer tabela completa: impede publicar só os nomes que o parser reconheceu.
    if abs(sum(r["percent"] for r in results + others) - 100) > 2:
        return None
    institute = institute_name(article)
    registration = re.search(r"\bBR-\d{5}/20\d{2}\b", text)
    confidence = re.search(r"(?:nivel de confianca|confianca)\s*(?:e\s+)?(?:de\s+)?(\d+(?:[,.]\d+)?)%", normalized)
    margin = re.search(r"margem de erro.{0,30}?(\d+(?:[,.]\d+)?|dois|tres|quatro)\s*pontos? percentuais", normalized)
    sample = re.search(r"ouviu\s+([\d.]+)\s+pessoas", normalized)
    period = re.search(r"(?:entre os dias|nos dias)\s+\d{1,2}\s+e\s+\d{1,2}\s+de\s+[a-z]+", normalized)
    if not all((institute, registration, confidence, margin, sample, period)):
        return None
    return {"institute": institute, "registration": registration.group(), "confidence": confidence.group(1) + "%", "margin": margin.group(1) + " pontos percentuais", "sample": sample.group(1), "period": period.group(), "results": sorted(results, key=lambda row: row["candidate"]), "others": others, "scope": "Presidente · Brasil · 2º turno · votos totais"}


def as_alert(article, poll):
    lines = [poll["scope"], "", "**Percentuais publicados (ordem alfabética):**"]
    if poll.get("notice"):
        lines = [poll["scope"], "", "Nova notícia de pesquisa encontrada. Percentuais não publicados neste alerta porque a tabela não pôde ser extraída e validada. Consulte a matéria no link."]
    for row in poll["results"]:
        lines.append(f"{row['candidate']} ({row['party']}): {row['percent']:g}%")
    for row in poll["others"]:
        lines.append(f"{row['label']}: {row['percent']:g}%")
    if poll.get("notice"):
        lines += ["", f"Instituto: {poll['institute']}", f"Registro informado pela matéria: {poll['registration']}", "", "Fonte: " + article["title"]]
        return {**article, "description": article["description"][:450], "alert_title": "Nova pesquisa — consulte os resultados na fonte", "message": "\n".join(lines), "footer": "Aviso de notícia com registro BR; tabela não validada automaticamente. Não há percentuais extraídos neste alerta."}
    lines += ["", f"Instituto: {poll['institute']}", f"Coleta: {poll['period']}", f"Amostra: {poll['sample']} pessoas", f"Margem de erro: {poll['margin']}", f"Confiança: {poll['confidence']}", f"Registro informado pela matéria: {poll['registration']}", "", "Fonte: " + article["title"]]
    return {**article, "description": article["description"][:450], "alert_title": "Pesquisa de intenção de voto — presidente", "message": "\n".join(lines), "footer": "Percentuais transcritos da matéria; base de votos indicada acima. Registro informado pela fonte, sem validação automática no TSE."}


def institute_name(article):
    title = article['title']
    name = next((n for n in INSTITUTES if normalize(n) in normalize(title)), None)
    if name:
        return name
    # Novos institutos não precisam ser incluídos no catálogo: nome explícito.
    match = re.match(r'Pesquisa\s+([A-ZÀ-Ý][\wÀ-ÿ /&.-]{1,60}?)(?=\s*[:,–—]|\s+(?:mostra|aponta|indica|revela)\b)', title)
    if match:
        return match.group(1).strip()
    prefix = re.match(r"([A-ZÀ-Ý][\wÀ-ÿ &/.-]{1,60})\s*:", title)
    return prefix.group(1).strip() if prefix and 'pesquisa' in normalize(article['description'][:2000]) else None


def national_scope(article):
    from tendencias_busca.estados import ESTADOS
    title = normalize(article['title'])
    for state in ESTADOS.values():
        if re.search(r"\b(?:no|na|em|do|da)\s+(?:estado d[eo]\s+)?" + re.escape(normalize(state)) + r"\b", title):
            return False
    text = normalize(article['description'])
    return bool(re.search(r"todo o pais|em todo o brasil|27 (?:unidades|estados)|pesquisa nacional|abrangencia nacional|territorio nacional", text))


def parse_valid_poll(article):
    text, title = article['description'], article['title']
    if not national_scope(article):
        return None
    normalized = normalize(text)
    if not re.search(r'(?:2[ºo°]?|segundo)\s*turno', normalize(title)):
        return None
    if not any(w in normalize(title + ' ' + text[:4000] + ' ' + article['url']) for w in ('presiden', 'presidencia')):
        return None
    # Exigir uma base explícita; nunca converter totais em válidos.
    if 'votos validos' not in normalize(title + ' ' + text[:4000]):
        return None
    name = institute_name(article)
    registration = re.search(r'\bBR-\d{5}/20\d{2}\b', text)
    confidence = re.search(r'(?:nivel|intervalo)?\s*de?\s*confianca\s*(?:e\s+)?(?:de\s+)?(\d+(?:[,.]\d+)?)\s*%', normalized)
    margin = re.search(r'margem de erro.{0,35}?(\d+(?:[,.]\d+)?|dois|tres|quatro)\s*pontos? percentua(?:l|is)', normalized)
    sample = re.search(r'(?:ouviu|entrevistou|foram entrevistad[oa]s)\s*([\d.]+)\s*(?:pessoas|eleitores|entrevistados)', normalized)
    if not sample:
        sample = re.search(r'(?:foram|com)\s*([\d.]+)\s*entrevistas', normalized)
    period = re.search(r'(?:(?:entre os dias|nos dias)\s+\d{1,2}\s+(?:e|a)\s+\d{1,2}\s+de\s+[a-z]+|de\s+\d{1,2}\s+a\s+\d{1,2}\s+de\s+[a-z]+)', normalized)
    if not all((name, registration, confidence, margin, sample, period)):
        return None
    # Empate explícito: dois nomes/partidos na mesma frase e um percentual
    # aplicado expressamente a cada candidato. Não ler percentuais históricos.
    results = None
    for sentence in re.split(r'(?<=[.!?])\s+', text[:5000]):
        norm = normalize(sentence)
        if not ('empatad' in norm and re.search(r'cada um|cada candidato', norm) and 'votos validos' in norm):
            continue
        numbers = re.findall(r'(\d{1,3}(?:[,.]\d+)?)\s*%', sentence)
        entries = re.findall(r'([A-ZÀ-Ý][A-Za-zÀ-ÿ .’\x27-]{1,100}?)\s*\(([A-Z][A-Z0-9 -]{0,20})\)', sentence)
        if len(entries) == 2 and len(numbers) == 1 and float(numbers[0].replace(',','.')) == 50:
            results = []
            for candidate, party in entries:
                # Remover cargos e oração introdutória, mantendo só o nome explícito.
                candidate = re.split(r'\b(?:presidente|senador|governador|candidato)\s+', candidate, flags=re.I)[-1].strip()
                results.append({'candidate':candidate, 'party':party, 'percent':50.0})
            break
    if results is None and 'votos validos' in normalize(title) and len(re.findall(r'\d+(?:[,.]\d+)?\s*%', title)) == 2:
        # O título declara dois números atuais; nomes/partidos devem constar
        # do corpo. Só associar aliases inequívocos presentes no nome completo.
        people = re.findall(r"([A-ZÀ-Ý][A-Za-zÀ-ÿ .’'-]{1,100}?)\s*\(([A-Z][A-Z0-9 -]{0,20})\)", text[:3500])
        found = {}
        for candidate, party in people:
            candidate = re.split(r'\b(?:presidente|senador|governador|candidato)\s+',candidate,flags=re.I)[-1].strip()
            if len(candidate.split()) > 8:
                continue
            for alias in [candidate, *candidate.split()]:
                if len(alias) < 3:
                    continue
                hit = re.search(r"\b" + re.escape(normalize(alias)) + r"\b\s*(?:[,;:]|tem|com|marca|registra|recebe|pontua)?\s*(\d+(?:[,.]\d+)?)\s*%",normalize(title))
                if hit:
                    found[candidate] = {'candidate':candidate,'party':party,'percent':float(hit.group(1).replace(',','.'))}
        if len(found) == 2:
            results = list(found.values())
    if results is None:
        marker = re.search(r'votos v[aá]lidos\s*:', text, flags=re.I)
        if not marker:
            return None
        block = re.split(r'votos totais|Metodologia|Saiba mais|Veja tamb[eé]m', text[marker.end():], maxsplit=1,flags=re.I)[0][:800]
        entries = re.findall(r'([A-ZÀ-Ý][A-Za-zÀ-ÿ .’\x27-]{1,70})\s*\(([A-Z][A-Z0-9 -]{0,20})\)\s*:\s*(\d{1,3}(?:[,.]\d+)?)\s*%',block)
        results = [{'candidate':n.strip(),'party':p,'percent':float(v.replace(',','.'))} for n,p,v in entries]
    if len(results) != 2 or len({r['candidate'] for r in results}) != 2 or any(not 0<=r['percent']<=100 for r in results) or abs(sum(r['percent'] for r in results)-100)>1:
        return None
    return {'institute':name, 'registration':registration.group(), 'confidence':confidence.group(1)+'%',
            'margin':margin.group(1)+' pontos percentuais', 'sample':sample.group(1), 'period':period.group(),
            'results':sorted(results,key=lambda r:r['candidate']), 'others':[], 'base':'votos_validos',
            'scope':'Presidente · Brasil · 2º turno · votos válidos (excluem brancos/nulos/indecisos)'}


def parse_poll(article):
    if re.search(r"\b(?:governador|prefeito|senado|vereador)\b", normalize(article['title'])):
        return None
    total = parse_total_poll(article)
    if total:
        return dict(total, base='votos_totais')
    return parse_valid_poll(article)


def parse_notice(article):
    """Aviso sem percentuais quando a matéria não permite validar uma tabela."""
    title, text = article['title'], article['description']
    if re.search(r"\b(?:governador|prefeito|senado|vereador)\b", normalize(title)):
        return None
    if not matches_poll(title, text) or not re.search(r'(?:2[ºo°]?|segundo)\s*turno', normalize(title)):
        return None
    if not any(w in normalize(title+' '+text[:2000]) for w in ('presidente', 'presidencia')):
        return None
    registration = re.search(r'\bBR-\d{5}/20\d{2}\b', text)
    if not registration or not national_scope(article):
        return None
    return {'institute':institute_name(article) or 'Não identificado automaticamente — consulte a fonte',
            'registration':registration.group(), 'scope':'Presidente · Brasil · 2º turno · tabela não extraída com segurança',
            'results':[], 'others':[], 'base':'nao_extraida', 'notice':True,
            'confidence':'Não extraído', 'margin':'Não extraída', 'sample':'Não extraída', 'period':'Não extraído'}
