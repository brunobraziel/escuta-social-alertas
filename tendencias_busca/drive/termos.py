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
    clusters = data.get("clusters")
    if clusters is not None:
        if not isinstance(clusters, list) or not clusters:
            raise ValueError("Clusters inválidos")
        ids, grouped = [], []
        for cluster in clusters:
            if not isinstance(cluster, dict) or not isinstance(cluster.get("id"), str) or not isinstance(cluster.get("terms"), list) or not 1 <= len(cluster["terms"]) <= 5:
                raise ValueError("Cada cluster deve ter ID e de 1 a 5 termos")
            ids.append(cluster["id"])
            grouped.extend(cluster["terms"])
        if len(set(ids)) != len(ids) or grouped != terms:
            raise ValueError("Clusters devem cobrir a lista de termos na mesma ordem, sem duplicatas")
    if data.get("mode") in ("filter_trending", "clusters_daily") and not clusters:
        raise ValueError("Filtro exige clusters")
    if data.get("mode") == "clusters_daily" and len(clusters) > 9:
        raise ValueError("No máximo nove clusters por coleta diária")
    if data.get("mode") == "clusters_daily" and any("," in t for t in terms):
        raise ValueError("Termos com vírgula não suportados")
    return {**data, "terms": terms}
