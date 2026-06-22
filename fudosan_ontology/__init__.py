"""fudosan-ontology — 不動産 業界用語・名寄せオントロジー。

辞書(ontology.json) + 名寄せ/正規化ハーネス(ontology.py) + MCP サーバ(mcp_server.py)。
"""
__version__ = "0.1.0"
__all__ = ["load_ontology", "norm_key", "process", "KINDS", "__version__"]


def __getattr__(name):  # 遅延ロード（-m 実行時の二重import警告を避ける）
    if name in ("load_ontology", "norm_key", "process", "KINDS"):
        from . import ontology
        return getattr(ontology, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
