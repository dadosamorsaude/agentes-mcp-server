"""
Tool: query_athena — Consulta SQL no AWS Athena com validação por agent_id.
"""

import asyncio
import json
import re
import logging

from pyathena import connect

from config.settings import settings
from config.agents import AGENT_CONFIGS

logger = logging.getLogger(__name__)

ROW_FETCH_LIMIT = settings.ATHENA_MAX_ROWS


# ──────────────────────────────────────────────────────────────────────────────
# Validação SQL
# ──────────────────────────────────────────────────────────────────────────────

def _strip_sql_comments(sql: str) -> str:
    """Remove comentários /* ... */ e -- ... para validações mais robustas."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return no_line


def validate_sql_generic(sql: str) -> None:
    """Validação genérica: somente SELECT, sem SELECT *."""
    cleaned = _strip_sql_comments(sql)
    sql_upper = cleaned.upper()

    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE "]
    if any(token in sql_upper for token in forbidden):
        raise ValueError("SQL contém operação proibida. Apenas SELECT é permitido.")

    if "SELECT *" in sql_upper:
        raise ValueError(
            "SELECT * não é permitido. Por favor, liste as colunas explicitamente."
        )


def validate_sql_for_agent(sql: str, agent_id: str) -> None:
    """Validação genérica + regras específicas do agente."""
    validate_sql_generic(sql)

    config = AGENT_CONFIGS.get(agent_id, {})
    cleaned = _strip_sql_comments(sql)
    sql_upper = cleaned.upper()

    # Filtro obrigatório (ex: id_especialidade = 616 para Cora)
    mandatory = config.get("sql_mandatory_filter")
    if mandatory:
        pattern = mandatory.upper().replace("=", r"\s*=\s*")
        if not re.search(pattern, sql_upper):
            raise ValueError(
                f"Filtro obrigatório ausente para agente '{agent_id}': "
                f"toda consulta DEVE incluir `{mandatory}` no WHERE."
            )


# ──────────────────────────────────────────────────────────────────────────────
# Execução
# ──────────────────────────────────────────────────────────────────────────────

def _execute_athena_query(sql: str) -> tuple[list[dict], bool]:
    """Executa a query e devolve (linhas, atingiu_limite)."""
    conn = None
    cursor = None
    try:
        conn = connect(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.aws_region_clean,
            s3_staging_dir=settings.ATHENA_S3_STAGING_DIR,
            schema_name=settings.ATHENA_DATABASE,
        )
        cursor = conn.cursor()
        cursor.execute(sql)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchmany(ROW_FETCH_LIMIT + 1)
        hit_limit = len(rows) > ROW_FETCH_LIMIT
        if hit_limit:
            rows = rows[:ROW_FETCH_LIMIT]

        results = [dict(zip(columns, row)) for row in rows]
        return results, hit_limit

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


async def query_athena(sql: str, agent_id: str) -> str:
    """
    Executa consulta SQL no AWS Athena com validações específicas do agente.

    O parâmetro agent_id determina filtros obrigatórios e restrições.
    Agentes válidos: cora, amorzito, iris, auxiliar-medico.

    Args:
        sql: Consulta SQL compatível com Presto/Athena. Apenas SELECT é permitido.
        agent_id: Identificador do agente que está solicitando a consulta.

    Returns:
        JSON com os resultados da consulta ou mensagem de erro.
    """
    config = AGENT_CONFIGS.get(agent_id)
    if not config:
        return f"Erro: agente '{agent_id}' não registrado no servidor MCP."

    if not config.get("has_athena"):
        return f"Erro: agente '{agent_id}' não possui permissão para consultar o Athena."

    try:
        validate_sql_for_agent(sql, agent_id)
    except ValueError as e:
        logger.warning(f"SQL inválido rejeitado | agent={agent_id} | erro={e}")
        return f"Consulta inválida: {str(e)}"

    logger.info(f"query_athena | agent={agent_id} | sql={sql[:120]}...")

    try:
        results, hit_limit = await asyncio.to_thread(_execute_athena_query, sql)

        row_count = len(results)
        if not results:
            return "Nenhum resultado encontrado para esta consulta."

        logger.info(
            f"query_athena | agent={agent_id} | rows={row_count} | limit_hit={hit_limit}"
        )

        payload = {
            "row_count": row_count,
            "row_limit_hit": hit_limit,
            "rows": results,
        }
        if hit_limit:
            payload["warning"] = (
                f"LIMITE DE LINHAS ATINGIDO ({ROW_FETCH_LIMIT}). "
                "Pode haver mais registros não retornados. "
                "Refine com filtros mais estritos ou use COUNT/GROUP BY."
            )

        return json.dumps(payload, ensure_ascii=False, default=str)

    except Exception as e:
        logger.exception(f"Erro na query Athena | agent={agent_id}")
        return (
            f"Erro ao acessar o banco de dados Athena: {str(e)}. "
            "Verifique se as credenciais e o nome do banco estão corretos."
        )
