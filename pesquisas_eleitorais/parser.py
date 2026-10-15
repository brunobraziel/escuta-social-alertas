"""Extração conservadora de tabela explícita de votos totais, sem inferir resultados."""
import re
from core.alerta import normalize

INSTITUTES = ("Datafolha", "Quaest", "AtlasIntel", "Ipec", "Ipsos", "Paraná Pesquisas", "Real Time Big Data", "Futura")


def matches_poll(title, description):
    text = normalize(title)
    if any(word in text for word in ("rejei", "aprov", "desaprov", "problemas", "preocupac")):
        return False
    return ("intenc" in text and "voto" in text) or (any(normalize(name) in text for name in INSTITUTES) and "%" in text)


def parse_poll(article):
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
    institute = next((name for name in INSTITUTES if normalize(name) in normalize(article["title"])), None)
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
    for row in poll["results"]:
        lines.append(f"{row['candidate']} ({row['party']}): {row['percent']:g}%")
    for row in poll["others"]:
        lines.append(f"{row['label']}: {row['percent']:g}%")
    lines += ["", f"Instituto: {poll['institute']}", f"Coleta: {poll['period']}", f"Amostra: {poll['sample']} pessoas", f"Margem de erro: {poll['margin']}", f"Confiança: {poll['confidence']}", f"Registro informado pela matéria: {poll['registration']}", "", "Fonte: " + article["title"]]
    return {**article, "description": article["description"][:450], "alert_title": "Pesquisa de intenção de voto — presidente", "message": "\n".join(lines), "footer": "Notícia elegível mais recente nos feeds consultados; não garante última pesquisa nacional. Sem previsão ou comparação."}
