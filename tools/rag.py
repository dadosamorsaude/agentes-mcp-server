"""
Tool: search_rag — Busca semântica unificada no Pinecone com escopo por agent_id.
"""

import json
import logging

from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

from config.settings import settings
from config.agents import AGENT_CONFIGS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Infraestrutura Pinecone (singletons)
# ──────────────────────────────────────────────────────────────────────────────

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


def _get_pinecone() -> Pinecone | None:
    global _pc_client
    if _pc_client is None:
        if not settings.PINECONE_API_KEY:
            return None
        _pc_client = Pinecone(api_key=settings.PINECONE_API_KEY)
    return _pc_client


def _get_retriever(index_name: str, namespace: str, k: int):
    """Cria um retriever LangChain Pinecone para um índice/namespace específico."""
    pc = _get_pinecone()
    if pc is None:
        return None

    index = pc.Index(index_name)
    vectorstore = PineconeVectorStore(
        index=index,
        embedding=_get_embeddings(),
        namespace=namespace,
        text_key="text",
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})


def _format_docs(docs) -> str:
    """Formata os documentos recuperados com metadados de fonte."""
    if not docs:
        return ""

    formatted = []
    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        fonte = metadata.get("fonte", "Fonte não informada")
        artigo = metadata.get("artigo", "")
        tema = metadata.get("tema", "")
        capitulo = metadata.get("capitulo", "")
        secao = metadata.get("secao", "")

        header = f"[Trecho {i}]\nFonte: {fonte}\n"
        if capitulo:
            header += f"Capítulo: {capitulo}\n"
        if secao:
            header += f"Seção: {secao}\n"
        if artigo:
            header += f"Artigo: {artigo}\n"
        if tema:
            header += f"Tema: {tema}\n"

        formatted.append(f"{header}\nConteúdo:\n{doc.page_content}")

    return "\n\n---\n\n".join(formatted)


# ──────────────────────────────────────────────────────────────────────────────
# Tool principal
# ──────────────────────────────────────────────────────────────────────────────

def search_rag(query: str, agent_id: str, namespace_key: str = "", k: int = 5) -> str:
    """
    Busca semântica no Pinecone para documentos de referência (diretrizes, normas, protocolos).

    O agent_id determina quais índices e namespaces Pinecone são permitidos.
    O namespace_key seleciona qual base de conhecimento usar.

    Args:
        query: Texto da busca semântica.
        agent_id: Identificador do agente (cora, amorzito, iris, auxiliar-medico).
        namespace_key: Chave do namespace a buscar (ex: 'cfm', 'regras', 'has', 'catarata').
                       Se vazio, busca em TODOS os namespaces autorizados do agente.
        k: Número de documentos a retornar por namespace (padrão: 5).

    Returns:
        Texto formatado com os documentos encontrados ou mensagem de erro.
    """
    config = AGENT_CONFIGS.get(agent_id)
    if not config:
        return f"Erro: agente '{agent_id}' não registrado."

    allowed_namespaces = config.get("rag_namespaces", {})
    if not allowed_namespaces:
        return f"Erro: agente '{agent_id}' não possui namespaces RAG configurados."

    # Se namespace_key fornecido, valida permissão
    if namespace_key:
        if namespace_key not in allowed_namespaces:
            available = ", ".join(allowed_namespaces.keys())
            return (
                f"Namespace '{namespace_key}' não autorizado para agente '{agent_id}'. "
                f"Namespaces disponíveis: {available}"
            )
        namespaces_to_search = {namespace_key: allowed_namespaces[namespace_key]}
    else:
        namespaces_to_search = allowed_namespaces

    all_docs = []
    search_details = []

    for ns_key, ns_config in namespaces_to_search.items():
        index_name = settings.resolve_env(ns_config["index_env"])
        namespace = settings.resolve_env(ns_config["namespace_env"])

        if not index_name:
            logger.warning(
                f"search_rag | index_env={ns_config['index_env']} não configurado, pulando."
            )
            continue

        retriever = _get_retriever(index_name, namespace, k)
        if not retriever:
            logger.warning(f"search_rag | Pinecone não configurado para {ns_key}")
            continue

        try:
            docs = retriever.invoke(query)
            all_docs.extend(docs)
            search_details.append({
                "namespace_key": ns_key,
                "description": ns_config.get("description", ""),
                "docs_found": len(docs),
            })
            logger.info(
                f"search_rag | agent={agent_id} | ns={ns_key} | docs={len(docs)}"
            )
        except Exception as e:
            logger.error(f"search_rag | Erro no namespace {ns_key}: {e}")
            search_details.append({
                "namespace_key": ns_key,
                "error": str(e),
            })

    if not all_docs:
        searched = ", ".join(ns_key for ns_key in namespaces_to_search)
        return f"Nenhum documento encontrado nos namespaces buscados: {searched}."

    return _format_docs(all_docs)
