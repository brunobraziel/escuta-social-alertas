"""Diagnóstico isolado: sem Discord, sem estado e sem resultados privados nos logs."""
import re

from tendencias_busca.drive.termos import load_terms
from tendencias_busca.estados import ESTADOS
from tendencias_busca.google.coleta import trending, SourceUnavailable
from tendencias_busca.google.serpapi import compare_all
from tendencias_busca.janela import expired


def run():
    try:
        if expired():
            print("Período de coleta encerrado; sem consultas.")
            return
        snapshot = load_terms()
        print(f"Lista privada carregada: {len(snapshot['terms'])} termos. Valores omitidos.", flush=True)
        if snapshot.get("mode") == "clusters_daily":
            print("Modo diário: use replay para verificar o cache, ou test para coletar com persistência e limite diário. Probe não faz consultas pagas.")
            return
        if snapshot.get("mode") == "filter_trending":
            from tendencias_busca.filtro import filter_topics
            general = {uf: trending(uf) for uf in ("MG", "SP", "CE")}
            filtered = filter_topics(general, snapshot)
            print(f"RSS: {len(general)} UFs; {sum(bool(v) for v in filtered.values())} com correspondências; zero SerpApi. Sem envio.")
            return
        print("Uma tentativa de comparação; sem retentativas automáticas.", flush=True)
        result = compare_all(snapshot["terms"], list(ESTADOS))
        count = sum(bool(rows) for rows in result.values())
        print(f"Comparação concluída: {count}/{len(ESTADOS)} UFs com dados suficientes.", flush=True)
        if not count:
            raise SourceUnavailable("Sem dados suficientes")
        for uf in ("MG", "SP", "CE"):
            rows = trending(uf)
            print(f"RSS {uf}: {len(rows)} tendências recentes. Conteúdo omitido.", flush=True)
        print("Diagnóstico concluído. Nenhuma mensagem enviada ou estado alterado.")
    except Exception as error:
        # Não exibir traceback, URL, termos, payload ou credenciais em logs públicos.
        match = re.search(r"HTTP (\d{3})", str(error)) if isinstance(error, SourceUnavailable) else None
        detail = "HTTP " + match.group(1) if match else type(error).__name__
        print(f"Diagnóstico interrompido: {detail}. Sem novas tentativas, envio ou alteração de estado.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
