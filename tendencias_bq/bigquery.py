"""Leitura somente leitura das últimas ingestões de tabelas do BigQuery."""
import json
import os


PROJECT_ID = "comite-tecnologia"
DATASET_ID = "analise_redes"
TABLES = {"gtrends_em_alta_brasil", "gtrends_monitoramento_temas", "gtrends_monitoramento_cidades"}


class BigQueryUnavailable(RuntimeError):
    """Falha ao autenticar ou consultar o BigQuery."""


def _client():
    try:
        from google.cloud import bigquery

        raw_credentials = os.environ.get("BQ_SERVICE_ACCOUNT_JSON", "").strip()
        if raw_credentials:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                json.loads(raw_credentials),
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            return bigquery.Client(project=PROJECT_ID, credentials=credentials)
        return bigquery.Client(project=PROJECT_ID)
    except Exception as error:
        raise BigQueryUnavailable("Não foi possível configurar o cliente BigQuery") from error


def fetch_latest_ingestion(table_id):
    """Retorna o lote mais recente ingerido na última hora."""
    if table_id not in TABLES:
        raise ValueError("Tabela BigQuery não permitida")

    table = f"{PROJECT_ID}.{DATASET_ID}.{table_id}"
    query = f"""
        WITH latest AS (
          SELECT MAX(hora_ingestao) AS hora_ingestao
          FROM `{table}`
          WHERE hora_ingestao >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
        )
        SELECT *
        FROM `{table}`
        WHERE hora_ingestao = (SELECT hora_ingestao FROM latest)
        ORDER BY uf, aumento DESC, volume DESC, rotulo
    """
    if table_id == "gtrends_monitoramento_temas":
        # Cada linha recebe seu próprio timestamp; selecionar só MAX perderia o lote.
        query = f"""
            WITH latest AS (
              SELECT ingestao_id FROM `{table}`
              WHERE hora_ingestao >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                AND ingestao_id IS NOT NULL
              ORDER BY hora_ingestao DESC, ingestao_id DESC LIMIT 1
            )
            SELECT * FROM `{table}`
            WHERE ingestao_id = (SELECT ingestao_id FROM latest)
            ORDER BY macrotema, termo_base, lista, posicao, consulta
        """
    if table_id == "gtrends_monitoramento_cidades":
        query = f"""
            WITH latest AS (
              SELECT ingestao_id FROM `{table}`
              WHERE resolucao = 'REGION' AND job = 'estados'
                AND hora_ingestao >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                AND ingestao_id IS NOT NULL
              ORDER BY hora_ingestao DESC, ingestao_id DESC LIMIT 1
            )
            SELECT * FROM `{table}`
            WHERE ingestao_id = (SELECT ingestao_id FROM latest)
              AND resolucao = 'REGION' AND job = 'estados'
            ORDER BY uf, termo
        """
    try:
        rows = list(_client().query(query).result())
    except Exception as error:
        raise BigQueryUnavailable("Falha ao consultar a última ingestão do BigQuery") from error

    if not rows:
        return {"rows": [], "hora_ingestao": None, "ingestao_id": None}

    normalized_rows = [dict(row.items()) for row in rows]
    ingestion_times = {row["hora_ingestao"] for row in normalized_rows}
    ingestion_ids = {row.get("ingestao_id") for row in normalized_rows}
    if (table_id == "gtrends_em_alta_brasil" and len(ingestion_times) != 1) or len(ingestion_ids) != 1 or None in ingestion_ids:
        raise BigQueryUnavailable("A hora mais recente contém mais de uma ingestão")

    return {
        "rows": normalized_rows,
        "hora_ingestao": max(ingestion_times),
        "ingestao_id": next(iter(ingestion_ids)),
    }
