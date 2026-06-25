"""
Tool: evaluate_response — Avaliador LLM-as-Judge centralizado.

Usa critérios específicos por agente definidos em config/agents.py (EVALUATOR_CONFIGS).
"""

import json
import logging
from datetime import datetime, timezone

from openai import AsyncOpenAI

from config.settings import settings
from config.agents import AGENT_CONFIGS, EVALUATOR_CONFIGS

logger = logging.getLogger(__name__)

_async_client = None


def _get_async_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_client


def _format_rag_context(rag_context: list[dict] | None) -> str:
    """Formata o contexto RAG para inclusão no prompt do avaliador."""
    if not rag_context:
        return "Nenhuma diretriz normativa foi consultada nesta resposta."

    parts = []
    for item in rag_context:
        source = item.get("source", "Desconhecido")
        query = item.get("query", "")
        chunks = "\n---\n".join(item.get("chunks", []))
        parts.append(f"[{source}] Query: '{query}'\n{chunks}")
    return "\n\n".join(parts)


async def evaluate_response(
    agent_id: str,
    user_question: str,
    agent_response: str,
    raw_data: str = "",
    rag_context: str = "",
    chat_history: str = "",
) -> str:
    """
    Avalia a acurácia e qualidade da resposta de um agente via LLM-as-Judge.

    Usa critérios de avaliação específicos do agente (definidos no registry).
    Retorna JSON com score, sub-scores, flag de alucinação e justificativa.

    Args:
        agent_id: Identificador do agente avaliado (cora, amorzito, iris, auxiliar-medico).
        user_question: Pergunta original do usuário.
        agent_response: Resposta gerada pelo agente que está sendo avaliada.
        raw_data: Dados brutos do Athena (JSON string) ou transcrição original.
        rag_context: Contexto normativo recuperado do RAG (texto formatado).
        chat_history: Histórico da conversa para contexto.

    Returns:
        JSON com a avaliação completa incluindo score, sub-scores e justificativa.
    """
    eval_config = EVALUATOR_CONFIGS.get(agent_id)
    if not eval_config:
        return json.dumps({
            "score": 0,
            "aprovado": False,
            "erros_encontrados": [f"Agente '{agent_id}' não possui configuração de avaliação."],
            "justificativa": f"Agente '{agent_id}' não registrado no evaluator.",
        }, ensure_ascii=False)

    if not raw_data and not rag_context:
        empty_fields = eval_config.get("empty_evaluation_fields", {})
        result = {
            "score": 0,
            "aprovado": False,
            "erros_encontrados": ["Nenhum dado bruto ou contexto RAG disponível para avaliar."],
            "justificativa": "Avaliação impossível: sem dados de referência.",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "model": settings.MODEL_EVALUATOR,
            **empty_fields,
        }
        return json.dumps(result, ensure_ascii=False)

    # Monta o user message usando o template do agente
    template_kwargs = {
        "raw_data": raw_data or "Nenhum dado disponível.",
        "rag_context": rag_context or "Nenhuma diretriz normativa foi consultada.",
        "user_question": user_question,
        "agent_response": agent_response,
        "chat_history": chat_history or "Nenhum histórico anterior.",
    }

    user_message = eval_config["user_template"].format(**template_kwargs)

    try:
        client = _get_async_client()
        try:
            response = await client.chat.completions.create(
                model=settings.MODEL_EVALUATOR,
                temperature=settings.TEMPERATURE,
                messages=[
                    {"role": "system", "content": eval_config["system_prompt"]},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as e:
            # Se o modelo for do tipo reasoning/o1 ou a API reclamar de temperature, tenta sem temperature
            if "temperature" in str(e).lower() or "unsupported_value" in str(e).lower():
                logger.info(f"Modelo {settings.MODEL_EVALUATOR} não suporta parâmetro temperature. Reexecutando sem temperature.")
                response = await client.chat.completions.create(
                    model=settings.MODEL_EVALUATOR,
                    messages=[
                        {"role": "system", "content": eval_config["system_prompt"]},
                        {"role": "user", "content": user_message},
                    ],
                )
            else:
                raise


        raw_content = response.choices[0].message.content.strip()

        # Remove possíveis blocos de código markdown
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
            raw_content = raw_content.rsplit("```", 1)[0] if "```" in raw_content else raw_content

        evaluation = json.loads(raw_content.strip())
        evaluation["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        evaluation["model"] = settings.MODEL_EVALUATOR
        evaluation["agent_id"] = agent_id

        logger.info(
            f"evaluate_response | agent={agent_id} | score={evaluation.get('score')} "
            f"| aprovado={evaluation.get('aprovado')} "
            f"| alucinacao={evaluation.get('alucinacao_detectada', 'N/A')}"
        )
        return json.dumps(evaluation, ensure_ascii=False, default=str)

    except json.JSONDecodeError as e:
        logger.error(f"Avaliador: resposta do LLM não é JSON válido: {e}")
        return json.dumps(_empty_evaluation(
            agent_id, f"Falha ao parsear resposta do avaliador: {e}"
        ), ensure_ascii=False)

    except Exception as e:
        logger.exception(f"Avaliador: erro ao invocar LLM | agent={agent_id}")
        return json.dumps(_empty_evaluation(
            agent_id, f"Erro interno no avaliador: {e}"
        ), ensure_ascii=False)


def _empty_evaluation(agent_id: str, reason: str) -> dict:
    """Retorna uma avaliação vazia quando não é possível avaliar."""
    eval_config = EVALUATOR_CONFIGS.get(agent_id, {})
    empty_fields = eval_config.get("empty_evaluation_fields", {})
    return {
        "score": 0,
        "aprovado": False,
        "erros_encontrados": [reason],
        "justificativa": reason,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model": settings.MODEL_EVALUATOR,
        "agent_id": agent_id,
        **empty_fields,
    }
