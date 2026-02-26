"""Tests for shared.config."""
import os
from shared.config import Config


def test_config_defaults():
    cfg = Config()
    assert cfg.TRADING_MODE == "paper"
    assert cfg.MAX_CAPITAL == 1000.0
    assert cfg.MAX_OPEN_POSITIONS == 3
    assert cfg.is_live is False


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("MAX_CAPITAL", "500")
    monkeypatch.setenv("BINANCE_SYMBOLS", "btcusdt,ethusdt")
    cfg = Config.from_env()
    assert cfg.TRADING_MODE == "live"
    assert cfg.is_live is True
    assert cfg.MAX_CAPITAL == 500.0
    assert cfg.binance_symbols_list == ["btcusdt", "ethusdt"]


def test_config_binance_symbols_list():
    cfg = Config(BINANCE_SYMBOLS="btcusdt, ethusdt, solusdt")
    assert cfg.binance_symbols_list == ["btcusdt", "ethusdt", "solusdt"]
