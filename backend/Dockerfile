# Stage 1: the external, read-only documents MCP server (not written by us), pre-installed so the
# agent never needs the network at runtime.
FROM node:20-slim AS docs-mcp
RUN npm install -g @modelcontextprotocol/server-filesystem

# Stage 2: the app
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=docs-mcp /usr/local/bin/node /usr/local/bin/node
COPY --from=docs-mcp /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js /usr/local/bin/mcp-server-filesystem \
    && chmod +x /usr/local/lib/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js

WORKDIR /app

# deps first for better layer caching
COPY pyproject.toml ./
RUN mkdir -p app evals && touch app/__init__.py evals/__init__.py \
    && pip install -e ".[gemini,dev]"

COPY . .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
