FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copia os arquivos de dependência
COPY pyproject.toml uv.lock ./

# Sincroniza as dependências usando cache do uv
RUN uv sync --frozen --no-cache

# Copia o restante do código
COPY . .

# Expõe a porta do servidor MCP (conforme configurado em settings.py)
EXPOSE 8000

# Executa o servidor MCP via SSE
CMD ["uv", "run", "server.py"]
