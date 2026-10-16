"""Lê snapshot privado revisado do documento; não incorpora dados privados ao Git."""
import json
import os


def load_terms():
    raw = os.environ.get("ESCUTA_SOCIAL_TERMS_JSON", "")
    if not raw:
        raise RuntimeError("Configure ESCUTA_SOCIAL_TERMS_JSON com a lista revisada do Drive")
    data = json.loads(raw)
    terms = data.get("terms")
    if not isinstance(terms, list) or not 2 <= len(terms) <= 25:
        raise ValueError("A lista deve conter de 2 a 25 termos")
    if any(not isinstance(t, str) or not t.strip() or len(t) > 80 for t in terms):
        raise ValueError("Termos inválidos")
    terms = [t.strip() for t in terms]
    if len(set(t.casefold() for t in terms)) != len(terms):
        raise ValueError("Termos duplicados")
    if not data.get("source_modified") or not data.get("source_url", "").startswith("https://docs.google.com/document/d/"):
        raise ValueError("Informe documento de origem e data da versão revisada")
    return {**data, "terms": terms}
