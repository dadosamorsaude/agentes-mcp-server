"""
Tool: search_similar_records — Busca semântica de prontuários no Pinecone via embedding direto.
Usado pela Iris para ampliar recall de casos com variações de terminologia.
"""

import asyncio
import json
import logging

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

from config.settings import settings
from config.agents import AGENT_CONFIGS

logger = logging.getLogger(__name__)

_embeddings = None
_pc_client = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            api_key=settings.OPENAI_API_KEY,
            model="text-embedding-3-large",
            dimensions=3072,
        )
    return _embeddings


def _get_pinecone_index(index_name: str):
    global _pc_client
    if _pc_client is None:
        if not settings.PINECONE_API_KEY:
            return None
        _pc_client = Pinecone(api_key=settings.PINECONE_API_KEY)
    return _pc_client.Index(index_name)


def _search_pinecone(
    index_name: str, namespace: str, query_vector: list[float], top_k: int
) -> list:
    """Executa busca vetorial síncrona no Pinecone."""
    index = _get_pinecone_index(index_name)
    if index is None:
        return []
    result = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace,
    )
    return result.matches


async def search_similar_records(
    query: str, agent_id: str, top_k: int = 20
) -> str:
    """
    Busca prontuários clinicamente similares usando busca vetorial direta no Pinecone.

    Retorna IDs de atendimento para uso como filtro adicional em consultas SQL,
    ampliando o recall de casos com variações de terminologia clínica.

    Args:
        query: Representação clínica derivada do léxico RAG (ex: 'facectomia catarata LIO').
        agent_id: Identificador do agente. Somente agentes com has_semantic_search=True podem usar.
        top_k: Número máximo de resultados a retornar (padrão: 20).

    Returns:
        JSON com ids_atendimento, sugestão de filtro SQL e trechos encontrados.
    """
    config = AGENT_CONFIGS.get(agent_id)
    if not config:
        return json.dumps({
            "ids_atendimento": [],
            "total_encontrados": 0,
            "sugestao_sql_filter": "",
            "mensagem": f"Agente '{agent_id}' não registrado.",
        })

    if not config.get("has_semantic_search"):
        return json.dumps({
            "ids_atendimento": [],
            "total_encontrados": 0,
            "sugestao_sql_filter": "",
            "mensagem": f"Agente '{agent_id}' não possui permissão para busca semântica de prontuários.",
        })

    ss_config = config.get("semantic_search_config", {})
    index_name = settings.resolve_env(ss_config.get("index_env", ""))
    namespace = settings.resolve_env(ss_config.get("namespace_env", ""))

    if not index_name or not settings.PINECONE_API_KEY:
        return json.dumps({
            "ids_atendimento": [],
            "total_encontrados": 0,
            "sugestao_sql_filter": "",
            "mensagem": "Busca semântica indisponível (Pinecone não configurado).",
        })

    try:
        query_vector = await _get_embeddings().aembed_query(query)
        matches = await asyncio.to_thread(
            _search_pinecone, index_name, namespace, query_vector, top_k
        )

        if not matches:
            return json.dumps({
                "ids_atendimento": [],
                "total_encontrados": 0,
                "sugestao_sql_filter": "",
                "mensagem": (
                    "Nenhum prontuário similar encontrado no índice semântico. "
                    "Prossiga com a busca SQL usando regex normalmente."
                ),
            })

        ids = []
        trechos = []
        for match in matches:
            meta = match.metadata or {}
            id_atend = meta.get("id_atendimento")
            if not id_atend:
                continue
            ids.append(id_atend)
            trechos.append({
                "id_atendimento": id_atend,
                "score_similaridade": round(float(match.score), 4),
                "clinica": meta.get("clinica", ""),
                "regional": meta.get("regional", ""),
                "data_atendimento": meta.get("data_atendimento", ""),
                "trecho": meta.get("text", "")[:300],
            })

        sql_filter = f"id_atendimento IN ({', '.join(str(i) for i in ids)})" if ids else ""

        result = {
            "ids_atendimento": ids,
            "total_encontrados": len(ids),
            "sugestao_sql_filter": sql_filter,
            "instrucao": (
                "Use 'sugestao_sql_filter' como filtro adicional no SQL para "
                "ampliar o recall de casos clínicos com variações de terminologia."
            ),
            "trechos": trechos,
        }

        logger.info(
            f"search_similar_records | agent={agent_id} | found={len(ids)} "
            f"| query='{query[:60]}'"
        )
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Erro em search_similar_records | agent={agent_id}: {e}")
        return json.dumps({
            "ids_atendimento": [],
            "total_encontrados": 0,
            "sugestao_sql_filter": "",
            "mensagem": f"Erro na busca semântica: {str(e)}. Prossiga com SQL normalmente.",
        })
