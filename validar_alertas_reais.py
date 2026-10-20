"""Reenvia uma ocorrência real de cada alerta ativo, sem alterar o estado da rotina."""
import importlib
import json
import logging
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from main import load_catalog


def validate(entries, report_path):
    results = []
    with tempfile.TemporaryDirectory(prefix="alertas-validacao-") as directory:
        for entry in entries:
            if not entry["ativo"]:
                continue
            result = {"alert": entry["id"], "deliveries": [], "error": None}
            results.append(result)
            try:
                module = importlib.import_module(entry["modulo"])
                original_send = module.send_discord

                def send(webhook, article, site, test=False):
                    if test:
                        raise ValueError("Validação exige dados reais, sem exemplos fictícios")
                    if result["deliveries"]:
                        raise ValueError("Validação limitada a uma mensagem por alerta")
                    article = dict(article)
                    title = article.get("alert_title", "Escala 6x1 — próximos passos")
                    article["alert_title"] = "VALIDAÇÃO — dados reais · " + title
                    receipt = original_send(webhook, article, site, test=False)
                    result["deliveries"].append({
                        "source": site, "url": article["url"],
                        "published": article["published"], "discord": receipt,
                    })
                    return receipt

                args = ["--state", str(Path(directory) / (entry["id"] + ".json"))]
                if entry["id"] in ("escala_6x1", "pesquisa_presidente"):
                    args += ["--limit", "1"]
                with patch.object(module, "send_discord", side_effect=send):
                    module.run(args)
                if not result["deliveries"] and entry["id"] == "escala_6x1":
                    # Resultado real da consulta, sem inventar uma notícia para testar.
                    send(os.environ["DISCORD_WEBHOOK_URL"], {
                        "title": "Consulta real sem notícia elegível",
                        "alert_title": "Escala 6x1 — consulta concluída sem correspondências",
                        "url": "https://g1.globo.com/",
                        "published": datetime.now(timezone.utc).isoformat(),
                        "message": "**Resultado da consulta real**\n"
                                   "• **Fontes consultadas:** G1 e CNN Brasil.\n"
                                   "• **Janela:** últimas 48 horas.\n"
                                   "• **Notícias elegíveis:** nenhuma.\n"
                                   "• **Filtro:** escala 6x1 e próximos passos legislativos.\n"
                                   "• **Interpretação:** ausência de correspondências nos feeds; "
                                   "não confirma ausência de novidades fora dessas fontes.",
                        "footer": "Validação do envio. Nenhuma notícia fictícia; filtros da rotina preservados.",
                    }, "G1 e CNN Brasil · consulta RSS")
                    result["outcome"] = "no_matching_news"
                if not result["deliveries"]:
                    result["error"] = "Nenhuma ocorrência real elegível; nenhum exemplo foi inventado"
            except (Exception, SystemExit) as error:
                result["error"] = type(error).__name__
                logging.error("Validação de %s falhou (%s)", entry["id"], type(error).__name__)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return all(result["deliveries"] and not result["error"] for result in results)


if __name__ == "__main__":
    raise SystemExit(0 if validate(load_catalog(), Path(".generated/live-alert-validation.json")) else 1)
