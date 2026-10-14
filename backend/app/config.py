from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://longview:longview@localhost:5432/longview"

    llm_provider: str = "ollama"  # "ollama" | "gemini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    ollama_keep_alive: str = "30m"
    llm_num_ctx: int = 4096
    llm_timeout_s: float = 300.0
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    docs_dir: str = "/data/docs"
    docs_mcp_command: str = "mcp-server-filesystem"
    docs_mcp_args: str = ""

    agent_max_llm_steps: int = 4
    agent_max_rounds: int = 2

    mcp_transport: str = "streamable-http"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001
    learner_mcp_url: str = "http://localhost:8001/mcp"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
