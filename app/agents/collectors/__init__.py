"""
Data collectors for different sources.

This module provides collectors for:
- Registry sources (DaData, Casebook, InfoSphere)
- Web search sources (Perplexity, Tavily)
- Government sources (FNS, FSSP, Bankrot) [NEW in Sprint 5]
"""

from app.agents.collectors.base import (
    BaseCollector,
    CollectorResult,
    CompositeCollector,
)
from app.agents.collectors.registry import (
    DaDataCollector,
    CasebookCollector,
    InfoSphereCollector,
)
from app.agents.collectors.web_search import (
    PerplexityCollector,
    TavilyCollector,
)
from app.agents.collectors.government import (
    FNSCollector,
    FSSPCollector,
    BankrotCollector,
    collect_government_data,
)

# Registry of all available collectors
COLLECTOR_REGISTRY = {
    # Registry sources (commercial APIs)
    "dadata": DaDataCollector,
    "casebook": CasebookCollector,
    "infosphere": InfoSphereCollector,
    # Web search sources
    "perplexity": PerplexityCollector,
    "tavily": TavilyCollector,
    # Government sources (free APIs) [NEW]
    "fns": FNSCollector,
    "fssp": FSSPCollector,
    "bankrot": BankrotCollector,
}

__all__ = [
    # Base classes
    "BaseCollector",
    "CollectorResult",
    "CompositeCollector",
    # Registry collectors
    "DaDataCollector",
    "CasebookCollector",
    "InfoSphereCollector",
    # Web search collectors
    "PerplexityCollector",
    "TavilyCollector",
    # Government collectors [NEW]
    "FNSCollector",
    "FSSPCollector",
    "BankrotCollector",
    "collect_government_data",
    # Registry
    "COLLECTOR_REGISTRY",
]
