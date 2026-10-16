"""Snapshots de dados e texto, reutilizáveis sem consultar fontes externas."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def save_state(path, state):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(path)


def snapshot(general, monitored, report, source, origin="coleta", monitored_at=None):
    return {"schema_version": 1, "origin": origin, "collected_at": report["published"], "monitored_at": monitored_at or report["published"], "source_version": source["source_modified"], "terms_count": len(source["terms"]), "general": general, "monitored": monitored, "report": report, "delivery": None}


def read_snapshot(state_path, cache_file=None):
    if cache_file:
        result = json.loads(Path(cache_file).read_text())
    else:
        state = json.loads(Path(state_path).read_text())
        result = state.get("trends_last_snapshot")
    if not isinstance(result, dict) or result.get("schema_version") != 1 or not result.get("report"):
        raise ValueError("Nenhum snapshot disponível; não será feita coleta automaticamente")
    return result


def markdown(cached):
    report = cached["report"]
    return ("# " + report["alert_title"] + "\n\n"
            + "Coleta: " + cached["collected_at"] + "\n\n"
            + "Comparação monitorada: " + cached["monitored_at"] + "\n\n"
            + "Origem: " + cached["origin"] + "\n\n"
            + report["message"] + "\n\n" + report["details_message"]
            + "\n\n" + report["footer"] + "\n")


def export(state_path, output_dir):
    state = json.loads(Path(state_path).read_text())
    cached = state.get("trends_last_snapshot")
    if not cached:
        return
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "ultima_coleta.json").write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n")
    # Distingue última coleta do último envio confirmado.
    delivered = state.get("trends_last_delivered_snapshot", cached)
    (output / "ultima_mensagem.md").write_text(markdown(delivered))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    export(args.state, args.output_dir)
