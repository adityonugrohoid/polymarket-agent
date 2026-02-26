"""Configuration management for polymarket-agent."""
import os
from pydantic import BaseModel


class Config(BaseModel):
    """Application configuration loaded from environment variables."""
    TRADING_MODE: str = "paper"
    OLLAMA_HOST: str = "https://ollama.com"
    OLLAMA_API_KEY: str = ""
    LLM_MODEL_SENTIMENT: str = "nemotron-3-nano:30b"
    LLM_MODEL_GRADER: str = "qwen3-next:80b"
    LLM_MODEL_JUDGE: str = "gpt-oss:120b"
    LLM_MODEL_FALLBACK: str = "gemini-3-flash-preview"
    BINANCE_SYMBOLS: str = "btcusdt,ethusdt,solusdt"
    POLYMARKET_PRIVATE_KEY: str = ""
    POLYMARKET_CHAIN_ID: int = 137
    MIN_EDGE_PCT: float = 2.0
    MIN_SIGNAL_SCORE: float = 0.6
    MIN_CONFIDENCE: float = 0.6
    MAX_CAPITAL: float = 1000.0
    MAX_POSITION_SIZE: float = 50.0
    MAX_OPEN_POSITIONS: int = 3
    COOLDOWN_SECONDS: int = 300
    DASHBOARD_PORT: int = 8080
    DB_PATH: str = "data/trades.db"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            TRADING_MODE=os.getenv("TRADING_MODE", "paper"),
            OLLAMA_HOST=os.getenv("OLLAMA_HOST", "https://ollama.com"),
            OLLAMA_API_KEY=os.getenv("OLLAMA_API_KEY", ""),
            LLM_MODEL_SENTIMENT=os.getenv("LLM_MODEL_SENTIMENT", "nemotron-3-nano:30b"),
            LLM_MODEL_GRADER=os.getenv("LLM_MODEL_GRADER", "qwen3-next:80b"),
            LLM_MODEL_JUDGE=os.getenv("LLM_MODEL_JUDGE", "gpt-oss:120b"),
            LLM_MODEL_FALLBACK=os.getenv("LLM_MODEL_FALLBACK", "gemini-3-flash-preview"),
            BINANCE_SYMBOLS=os.getenv("BINANCE_SYMBOLS", "btcusdt,ethusdt,solusdt"),
            POLYMARKET_PRIVATE_KEY=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
            POLYMARKET_CHAIN_ID=int(os.getenv("POLYMARKET_CHAIN_ID", "137")),
            MIN_EDGE_PCT=float(os.getenv("MIN_EDGE_PCT", "2.0")),
            MIN_SIGNAL_SCORE=float(os.getenv("MIN_SIGNAL_SCORE", "0.6")),
            MIN_CONFIDENCE=float(os.getenv("MIN_CONFIDENCE", "0.6")),
            MAX_CAPITAL=float(os.getenv("MAX_CAPITAL", "1000")),
            MAX_POSITION_SIZE=float(os.getenv("MAX_POSITION_SIZE", "50")),
            MAX_OPEN_POSITIONS=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
            COOLDOWN_SECONDS=int(os.getenv("COOLDOWN_SECONDS", "300")),
            DASHBOARD_PORT=int(os.getenv("DASHBOARD_PORT", "8080")),
            DB_PATH=os.getenv("DB_PATH", "data/trades.db"),
        )

    @property
    def binance_symbols_list(self) -> list[str]:
        return [s.strip() for s in self.BINANCE_SYMBOLS.split(",") if s.strip()]

    @property
    def is_live(self) -> bool:
        return self.TRADING_MODE == "live"
