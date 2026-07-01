# Servidor MCP Centralizado — AmorSaúde

Servidor MCP (Model Context Protocol) centralizado que unifica as ferramentas de **consulta SQL (Athena)**, **busca semântica (Pinecone RAG)**, **busca de prontuários similares**, **transcrição de áudio (Whisper)** e **avaliação de qualidade (LLM-as-Judge)** para todos os agentes do ecossistema AmorSaúde.

## Agentes Suportados

| Agente | Athena | RAG | Busca Semântica | Transcrição | Evaluator |
|---|---|---|---|---|---|
| **Cora** | ✅ (Cardiologia/HAS) | HAS | ❌ | ❌ | ✅ Unificado |
| **Amorzito** | ✅ (Qualidade/IQRC) | CFM, Regras, RDC, HAS | ❌ | ❌ | ✅ Unificado |
| **Iris** | ✅ (Catarata) | Catarata, Vocabulário | ✅ | ❌ | ✅ Unificado |
| **Auxiliar Médico** | ❌ | CFM, Regras, RDC | ❌ | ✅ | ✅ Transcrição |

## Primitivas MCP

### 🔧 Tools (5)
- `query_athena_tool(sql, agent_id)` — Consulta SQL com validação por agente
- `search_rag_tool(query, agent_id, namespace_key, k)` — Busca semântica no Pinecone
- `search_similar_records_tool(query, agent_id, top_k)` — Busca de prontuários similares
- `transcribe_audio_tool(file_path, agent_id)` — Transcrição via Whisper
- `evaluate_response_tool(agent_id, ...)` — Avaliação LLM-as-Judge

### 📄 Resources (6)
- `agent://registry/list` — Lista todos os agentes
- `agent://{agent_id}/config` — Configuração do agente
- `agent://{agent_id}/sql-rules` — Regras SQL específicas
- `agent://{agent_id}/rag-namespaces` — Namespaces RAG disponíveis
- `agent://{agent_id}/schema` — Schema do banco de dados
- `agent://{agent_id}/evaluator-criteria` — Critérios de avaliação

### 💬 Prompts (3)
- `setup-agent(agent_id, data_hoje, data_ontem)` — System prompt completo do agente
- `build-sql-expert-prompt(agent_id)` — Prompt do sub-agente SQL
- `build-evaluator-prompt(agent_id)` — Prompt do avaliador LLM-as-Judge

## Setup

```bash
# 1. Instalar dependências
uv sync

# 2. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com os valores reais

# 3. Rodar o servidor (SSE)
uv run server.py

# 4. Testar com o MCP Inspector
npx @modelcontextprotocol/inspector uv run server.py
```

## Estrutura

```
central-mcp-server/
├── server.py               # Ponto de entrada FastMCP (SSE)
├── config/
│   ├── settings.py         # Variáveis de ambiente (Pydantic Settings)
│   └── agents.py           # Registry: AGENT_CONFIGS, PERSONAS, EVALUATOR_CONFIGS
├── tools/
│   ├── athena.py           # query_athena (validação + execução)
│   ├── rag.py              # search_rag (Pinecone unificado)
│   ├── semantic_search.py  # search_similar_records (embedding direto)
│   ├── transcription.py    # transcribe_audio (Whisper)
│   └── evaluator.py        # evaluate_response (LLM-as-Judge)
├── resources/
│   └── agent_resources.py  # Resources dinâmicos por agente
├── pyproject.toml
├── .env.example
└── README.md
```
