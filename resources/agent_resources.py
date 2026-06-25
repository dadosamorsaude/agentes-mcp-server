"""
Resources MCP — Dados de leitura dinâmicos por agente.

Expõe configurações, regras SQL, namespaces RAG e critérios de avaliação
como Resources do protocolo MCP, acessíveis via URIs parametrizadas.
"""

import json

from config.agents import AGENT_CONFIGS, AGENT_PERSONAS, EVALUATOR_CONFIGS


def get_agent_config(agent_id: str) -> str:
    """Retorna a configuração completa do agente: nome, descrição,
    capacidades habilitadas (Athena, transcrição, busca semântica)."""
    config = AGENT_CONFIGS.get(agent_id)
    if not config:
        return f"Agente '{agent_id}' não registrado no servidor MCP."

    # Retorna versão resumida sem dados internos de env
    public_config = {
        "agent_id": agent_id,
        "name": config["name"],
        "description": config["description"],
        "capabilities": {
            "athena": config.get("has_athena", False),
            "transcription": config.get("has_transcription", False),
            "semantic_search": config.get("has_semantic_search", False),
        },
        "rag_namespaces": list(config.get("rag_namespaces", {}).keys()),
    }
    return json.dumps(public_config, ensure_ascii=False, indent=2)


def get_sql_rules(agent_id: str) -> str:
    """Retorna as regras SQL específicas deste agente:
    filtros obrigatórios, exclusões de especialidade, status válidos."""
    config = AGENT_CONFIGS.get(agent_id, {})

    if not config.get("has_athena"):
        return f"Agente '{agent_id}' não possui acesso ao banco de dados."

    rules = []
    if config.get("sql_mandatory_filter"):
        rules.append(
            f"OBRIGATÓRIO: Toda query DEVE incluir WHERE {config['sql_mandatory_filter']}"
        )
    if config.get("sql_excluded_specialties"):
        ids = ", ".join(str(x) for x in config["sql_excluded_specialties"])
        rules.append(f"EXCLUIR: id_especialidade NOT IN ({ids})")
    if config.get("sql_valid_statuses"):
        ids = ", ".join(str(x) for x in config["sql_valid_statuses"])
        rules.append(f"FILTRAR: status_agendamento IN ({ids})")

    rules.append("PROIBIDO: SELECT * — liste colunas explicitamente.")
    rules.append("PROIBIDO: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.")

    return "\n".join(rules) if rules else "Sem restrições SQL adicionais para este agente."


def get_rag_namespaces(agent_id: str) -> str:
    """Retorna os namespaces Pinecone disponíveis para busca RAG deste agente,
    com descrição de cada base de conhecimento."""
    config = AGENT_CONFIGS.get(agent_id, {})
    namespaces = config.get("rag_namespaces", {})

    if not namespaces:
        return f"Agente '{agent_id}' não possui namespaces RAG configurados."

    result = {}
    for key, ns_config in namespaces.items():
        result[key] = ns_config.get("description", "Sem descrição")

    return json.dumps(result, ensure_ascii=False, indent=2)


def get_db_schema(agent_id: str) -> str:
    """Retorna o schema de banco de dados permitido para este agente,
    incluindo tabela e colunas permitidas."""
    config = AGENT_CONFIGS.get(agent_id, {})

    if not config.get("table"):
        return f"Agente '{agent_id}' não possui acesso ao banco de dados."

    columns = ", ".join(config.get("allowed_columns", []))
    return f"Table: {config['table']}\nAllowed Columns: {columns}"


def get_evaluator_criteria(agent_id: str) -> str:
    """Retorna os critérios de avaliação (LLM-as-Judge) configurados para este agente."""
    eval_config = EVALUATOR_CONFIGS.get(agent_id)
    if not eval_config:
        return f"Agente '{agent_id}' não possui critérios de avaliação configurados."

    return json.dumps({
        "agent_id": agent_id,
        "score_type": eval_config.get("score_type", "integer_100"),
        "empty_evaluation_fields": eval_config.get("empty_evaluation_fields", {}),
        "system_prompt_preview": eval_config["system_prompt"][:200] + "...",
    }, ensure_ascii=False, indent=2)


def list_agents() -> str:
    """Lista todos os agentes registrados no servidor MCP com suas capacidades."""
    agents = []
    for agent_id, config in AGENT_CONFIGS.items():
        agents.append({
            "agent_id": agent_id,
            "name": config["name"],
            "description": config["description"],
            "capabilities": {
                "athena": config.get("has_athena", False),
                "transcription": config.get("has_transcription", False),
                "semantic_search": config.get("has_semantic_search", False),
                "rag_namespaces": list(config.get("rag_namespaces", {}).keys()),
            },
        })
    return json.dumps(agents, ensure_ascii=False, indent=2)
