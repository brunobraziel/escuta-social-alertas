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


def fetch_previous_state_ingestion(current):
    """Último lote estadual anterior, sem misturar municípios ou snapshots."""
    from google.cloud import bigquery
    table = f"{PROJECT_ID}.{DATASET_ID}.gtrends_monitoramento_cidades"
    query = f"""
        WITH previous AS (
          SELECT ingestao_id, MAX(hora_ingestao) AS last_seen FROM `{table}`
          WHERE resolucao = 'REGION' AND job = 'estados'
            AND ingestao_id != @current_id
            AND hora_ingestao >= TIMESTAMP_SUB(@current_time, INTERVAL 48 HOUR)
          GROUP BY ingestao_id
          HAVING MAX(hora_ingestao) < @current_time
          ORDER BY last_seen DESC, ingestao_id DESC LIMIT 1
        )
        SELECT source.* FROM `{table}` AS source
        JOIN previous USING (ingestao_id)
        WHERE source.resolucao = 'REGION' AND source.job = 'estados'
        ORDER BY uf, termo
    """
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter('current_id', 'STRING', current['ingestao_id']),
        bigquery.ScalarQueryParameter('current_time', 'TIMESTAMP', current['hora_ingestao']),
    ])
    try:
        rows = [dict(row.items()) for row in _client().query(query, job_config=config).result()]
    except Exception as error:
        raise BigQueryUnavailable("Falha ao consultar lote estadual anterior") from error
    if not rows:
        return {'rows': [], 'hora_ingestao': None, 'ingestao_id': None}
    ids = {row.get('ingestao_id') for row in rows}
    if len(ids) != 1 or None in ids or current['ingestao_id'] in ids:
        raise BigQueryUnavailable("Lote anterior estadual ambíguo")
    return {'rows': rows, 'hora_ingestao': max(row['hora_ingestao'] for row in rows),
            'ingestao_id': next(iter(ids))}
