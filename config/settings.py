"""
Configurações centralizadas do servidor MCP AmorSaúde.
Carrega todas as variáveis de ambiente necessárias para Athena, Pinecone, OpenAI.
"""

from dotenv import load_dotenv
load_dotenv(override=True)

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # ── OpenAI ────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str
    MODEL_EVALUATOR: str = "gpt-5.5"
    TEMPERATURE: float = 0.0

    # ── AWS / Athena ──────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    ATHENA_DATABASE: str
    ATHENA_S3_STAGING_DIR: str
    ATHENA_MAX_ROWS: int = 5000

    # ── Pinecone ──────────────────────────────────────────────────────────
    PINECONE_API_KEY: Optional[str] = None

    # Índices
    PINECONE_INDEX_CFM: str = ""
    PINECONE_INDEX_POP: str = ""
    PINECONE_INDEX_HAS: str = ""
    PINECONE_RAG_INDEX: str = ""

    # Namespaces
    PINECONE_NAMESPACE_CFM: str = ""
    PINECONE_NAMESPACE_REGRAS: str = ""
    PINECONE_NAMESPACE_RDC: str = ""
    PINECONE_NAMESPACE_HAS: str = ""
    PINECONE_NS_TREINAMENTO: str = ""
    PINECONE_NS_VOCABULARIO: str = ""
    PINECONE_NS_PRONTUARIOS: str = ""

    # ── Servidor MCP ──────────────────────────────────────────────────────
    MCP_SERVER_PORT: int = 8000
    MCP_API_KEY: str = "mcp_sk_central_sec_placeholder_key"
    
    # IDs Gerados dos Agentes (UUIDs/Hashes) para ofuscação e segurança
    AGENT_ID_CORA: str = "agent-id-cora-uuid-placeholder"
    AGENT_ID_AMORZITO: str = "agent-id-amorzito-uuid-placeholder"
    AGENT_ID_IRIS: str = "agent-id-iris-uuid-placeholder"
    AGENT_ID_AUXILIAR_MEDICO: str = "agent-id-auxmed-uuid-placeholder"

    @property
    def aws_region_clean(self) -> str:
        return self.AWS_REGION.lstrip(":").strip()

    def resolve_env(self, env_name: str) -> str:
        """Resolve um nome de variável de ambiente para seu valor no settings."""
        return getattr(self, env_name, "")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
