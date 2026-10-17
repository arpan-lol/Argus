from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/python/.env"), extra="ignore")
    database_url: str = "postgresql://argus:argus_local@127.0.0.1:5434/argus"
    falkor_host: str = "127.0.0.1"
    falkor_port: int = 6379
    graph_name: str = "argus_sources_v2"
    legacy_graph_name: str = "materials_evidence_v1"
    data_dir: Path = Path(__file__).resolve().parents[3] / "data"
    uploads_dir: Path = Path(__file__).resolve().parents[3] / "data" / "uploads"
    frontend_origin: str = "http://localhost:3001"


settings = Settings()
