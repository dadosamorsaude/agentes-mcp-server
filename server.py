"""
Servidor MCP Centralizado — AmorSaúde

Ponto de entrada principal que registra todas as Tools, Resources e Prompts
do ecossistema de agentes no protocolo MCP via FastMCP + SSE.

Para rodar localmente:
    uv run server.py

Para testar com o Inspector:
    npx @modelcontextprotocol/inspector uv run server.py
"""

import json
import logging

from mcp.server.fastmcp import FastMCP

from config.settings import settings
from config.agents import AGENT_CONFIGS, AGENT_PERSONAS, EVALUATOR_CONFIGS, resolve_agent_id

from tools.athena import query_athena
from tools.rag import search_rag
from tools.semantic_search import search_similar_records
from tools.transcription import transcribe_audio
from tools.evaluator import evaluate_response

from resources.agent_resources import (
    get_agent_config,
    get_sql_rules,
    get_rag_namespaces,
    get_db_schema,
    get_evaluator_criteria,
    list_agents,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Inicialização do servidor MCP
# ══════════════════════════════════════════════════════════════════════════════

from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "AmorSaude-Central",
    instructions=(
        "Servidor MCP centralizado do ecossistema AmorSaúde. "
        "Fornece ferramentas de consulta SQL (Athena), busca semântica (Pinecone RAG), "
        "busca de prontuários similares, transcrição de áudio (Whisper) e "
        "avaliação de qualidade (LLM-as-Judge). "
        "Todas as ferramentas requerem um agent_id para validação de escopo."
    ),
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Ações executáveis
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def query_athena_tool(sql: str, agent_id: str) -> str:
    """Executa consulta SQL no AWS Athena com validações específicas do agente.

    O parâmetro agent_id determina filtros obrigatórios e restrições de segurança.
    Agentes válidos: cora, amorzito, iris.

    Args:
        sql: Consulta SQL compatível com Presto/Athena. Apenas SELECT é permitido.
        agent_id: Identificador do agente (ex: cora, amorzito, iris).
    """
    resolved_id = resolve_agent_id(agent_id)
    return await query_athena(sql, resolved_id)


@mcp.tool()
def search_rag_tool(
    query: str, agent_id: str, namespace_key: str = "", k: int = 5
) -> str:
    """Busca semântica no Pinecone para documentos de referência (diretrizes, normas, protocolos).

    O agent_id determina quais bases de conhecimento são permitidas.
    O namespace_key seleciona qual base buscar (ex: 'cfm', 'regras', 'has', 'catarata').
    Se namespace_key estiver vazio, busca em TODOS os namespaces autorizados do agente.

    Args:
        query: Texto da busca semântica.
        agent_id: Identificador do agente (ex: cora, amorzito, iris, auxiliar-medico).
        namespace_key: Chave do namespace (ex: cfm, regras, has, rdc, catarata). Vazio = todos.
        k: Número de documentos a retornar por namespace (padrão: 5).
    """
    resolved_id = resolve_agent_id(agent_id)
    return search_rag(query, resolved_id, namespace_key, k)


@mcp.tool()
async def search_similar_records_tool(
    query: str, agent_id: str, top_k: int = 20
) -> str:
    """Busca prontuários clinicamente similares via embedding vetorial no Pinecone.

    Retorna IDs de atendimento para uso como filtro adicional em consultas SQL.
    Somente agentes com busca semântica habilitada podem usar (ex: iris).

    Args:
        query: Representação clínica derivada do léxico RAG (ex: 'facectomia catarata LIO').
        agent_id: Identificador do agente (somente iris possui esta permissão).
        top_k: Número máximo de resultados (padrão: 20).
    """
    resolved_id = resolve_agent_id(agent_id)
    return await search_similar_records(query, resolved_id, top_k)


@mcp.tool()
def transcribe_audio_tool(file_path: str, agent_id: str) -> str:
    """Transcreve um arquivo de áudio usando OpenAI Whisper.

    Somente agentes com transcrição habilitada podem usar (ex: auxiliar-medico).

    Args:
        file_path: Caminho completo para o arquivo de áudio.
        agent_id: Identificador do agente (ex: auxiliar-medico).
    """
    resolved_id = resolve_agent_id(agent_id)
    return transcribe_audio(file_path, resolved_id)


@mcp.tool()
async def evaluate_response_tool(
    agent_id: str,
    user_question: str,
    agent_response: str,
    raw_data: str = "",
    rag_context: str = "",
    chat_history: str = "",
) -> str:
    """Avalia a qualidade da resposta de um agente via LLM-as-Judge.

    Usa critérios específicos por agente: Cora/Amorzito/Iris usam Precisão Factual (35)
    + Completude (25) + Interpretação Clínica (25) + Aplicação Normativa (15) +
    Detecção de Alucinação/Vazamento. Auxiliar Médico usa Fidelidade Clínica (40)
    + Estruturação (30) + Aplicação Normativa (30).

    Args:
        agent_id: Identificador do agente avaliado.
        user_question: Pergunta original do usuário.
        agent_response: Resposta do agente que está sendo avaliada.
        raw_data: Dados brutos do Athena (JSON) ou transcrição original.
        rag_context: Contexto normativo recuperado do RAG.
        chat_history: Histórico da conversa.
    """
    resolved_id = resolve_agent_id(agent_id)
    return await evaluate_response(
        resolved_id, user_question, agent_response, raw_data, rag_context, chat_history
    )


# ══════════════════════════════════════════════════════════════════════════════
# RESOURCES — Dados de leitura por agente
# ══════════════════════════════════════════════════════════════════════════════

@mcp.resource("agent://registry/list")
def resource_list_agents() -> str:
    """Lista todos os agentes registrados no servidor MCP com suas capacidades."""
    return list_agents()


@mcp.resource("agent://{agent_id}/config")
def resource_agent_config(agent_id: str) -> str:
    """Configuração completa do agente: nome, descrição e capacidades habilitadas."""
    resolved_id = resolve_agent_id(agent_id)
    return get_agent_config(resolved_id)


@mcp.resource("agent://{agent_id}/sql-rules")
def resource_sql_rules(agent_id: str) -> str:
    """Regras SQL específicas: filtros obrigatórios, exclusões de especialidade, status válidos."""
    resolved_id = resolve_agent_id(agent_id)
    return get_sql_rules(resolved_id)


@mcp.resource("agent://{agent_id}/rag-namespaces")
def resource_rag_namespaces(agent_id: str) -> str:
    """Namespaces Pinecone disponíveis para busca RAG com descrição de cada base."""
    resolved_id = resolve_agent_id(agent_id)
    return get_rag_namespaces(resolved_id)


@mcp.resource("agent://{agent_id}/schema")
def resource_db_schema(agent_id: str) -> str:
    """Schema do banco de dados: tabela e colunas permitidas para este agente."""
    resolved_id = resolve_agent_id(agent_id)
    return get_db_schema(resolved_id)


@mcp.resource("agent://{agent_id}/evaluator-criteria")
def resource_evaluator_criteria(agent_id: str) -> str:
    """Critérios de avaliação LLM-as-Judge configurados para este agente."""
    resolved_id = resolve_agent_id(agent_id)
    return get_evaluator_criteria(resolved_id)


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS — Templates de instrução centralizados
# ══════════════════════════════════════════════════════════════════════════════

FIDELIDADE_NUMERICA = """
## Diretrizes de Fidelidade Numérica e Integridade de Sessão
1. Fidelidade Numérica Absoluta: Transcreva números exatamente como retornados pelas ferramentas. Nunca arredonde, estime ou modifique valores.
2. Especificação da Métrica de Contagem: Sempre diferencie "atendimentos/consultas" de "pacientes únicos".
3. Menção de Período Temporal: Sempre informe o período de data_atendimento considerado.
4. Identificadores Reais: Exiba apenas identificadores reais (id_paciente, id_atendimento) retornados pelas consultas. Proibido alucinar CPFs, nomes ou IDs fictícios.
5. Consistência de Filtros em Histórico: Mantenha consistência de filtros entre perguntas consecutivas na mesma sessão, exceto se o usuário solicitar alteração.
"""


@mcp.prompt()
def setup_agent(
    agent_id: str, data_hoje: str = "", data_ontem: str = ""
) -> str:
    """Monta o system prompt completo para o agente especificado.

    Combina: persona do agente + regras de fidelidade numérica + regras SQL
    específicas + datas dinâmicas. Use este prompt para configurar o LLM do agente.

    Args:
        agent_id: Identificador do agente (cora, amorzito, iris, auxiliar-medico).
        data_hoje: Data de hoje no formato YYYY-MM-DD.
        data_ontem: Data de ontem no formato YYYY-MM-DD.
    """
    resolved_id = resolve_agent_id(agent_id)
    persona = AGENT_PERSONAS.get(resolved_id, "Agente não configurado.")
    config = AGENT_CONFIGS.get(resolved_id, {})

    sql_section = ""
    if config.get("has_athena"):
        sql_rules_text = get_sql_rules(resolved_id)
        sql_section = f"\n## Regras SQL Específicas\n{sql_rules_text}\n"

    return f"""{persona}
{FIDELIDADE_NUMERICA}
{sql_section}
## Date Reference
Today: {data_hoje}
Yesterday: {data_ontem}
"""


@mcp.prompt()
def build_sql_expert_prompt(agent_id: str) -> str:
    """Monta o prompt do sub-agente SQL (Athena) com as regras específicas do agente pai.

    Exemplo: Para Cora, inclui 'id_especialidade = 616' obrigatório.
    Para Amorzito, inclui exclusões de especialidades e status válidos.

    Args:
        agent_id: Identificador do agente pai (cora, amorzito, iris).
    """
    resolved_id = resolve_agent_id(agent_id)
    rules = get_sql_rules(resolved_id)
    schema = get_db_schema(resolved_id)

    return f"""You are an SQL specialist for AWS Athena. Return the requested information.

## Database Schema
{schema}

## Agent-Specific Rules
{rules}

## General SQL Rules
- NEVER use SELECT *. List columns explicitly.
- Use DATE 'YYYY-MM-DD' for date filters directly. Do NOT use CAST(data_atendimento AS DATE).
- Use COUNT(DISTINCT id_atendimento) for visits/appointments.
- Use COUNT(DISTINCT id_paciente) for unique patients.
- Never use COUNT(*) generically.
- Do NOT mix data types in COALESCE.
- NEVER reference a column alias inside the same SELECT list it is defined in.

## Output Rules
- ALWAYS return the exact data/rows returned by the query. Do NOT omit rows.
- NEVER ask questions or suggest options. Just return the fetched data.
"""


@mcp.prompt()
def build_evaluator_prompt(agent_id: str) -> str:
    """Retorna o system prompt do avaliador LLM-as-Judge para o agente especificado.

    Inclui os critérios de avaliação específicos (unificado para Cora/Amorzito/Iris,
    ou focado em transcrição para Auxiliar Médico).

    Args:
        agent_id: Identificador do agente a ser avaliado.
    """
    resolved_id = resolve_agent_id(agent_id)
    eval_config = EVALUATOR_CONFIGS.get(resolved_id)
    if not eval_config:
        return f"Agente '{resolved_id}' não possui critérios de avaliação configurados."
    return eval_config["system_prompt"]


# ══════════════════════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Iniciando servidor MCP AmorSaúde-Central via SSE...")
    import uvicorn
    # FastMCP exposes the SSE ASGI app via sse_app()
    app = mcp.sse_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.MCP_SERVER_PORT)


