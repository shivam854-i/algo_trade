"""SYNAPSE-TITAN Quantitative Strategy & Opportunity Selection Package.

Modular systematic universe screening, multi-horizon parameter binding,
calibrated Net Expectancy evaluation, risk-adjusted ranking, Fractional Kelly
& RMT de-noised HRP capital allocation, and plain-language decision explainability.
"""

from src.strategy.decision_explainer import (
    DecisionExplainer,
    PlainLanguageExplanation,
)
from src.strategy.horizon_mapper import (
    HorizonMapper,
    HorizonParameters,
)
from src.strategy.portfolio_selector import (
    AllocationItem,
    PortfolioAllocationResult,
    PortfolioSelector,
)
from src.strategy.trade_evaluator import (
    TradeEvaluationResult,
    TradeEvaluator,
)
from src.strategy.trade_ranker import (
    RankedOpportunity,
    TradeRanker,
)
from src.strategy.universe_selector import (
    CandidateEvaluation,
    UniverseSelectionCriteria,
    UniverseSelectionResult,
    UniverseSelector,
)

__all__ = [
    "HorizonParameters",
    "HorizonMapper",
    "UniverseSelectionCriteria",
    "CandidateEvaluation",
    "UniverseSelectionResult",
    "UniverseSelector",
    "TradeEvaluationResult",
    "TradeEvaluator",
    "RankedOpportunity",
    "TradeRanker",
    "AllocationItem",
    "PortfolioAllocationResult",
    "PortfolioSelector",
    "PlainLanguageExplanation",
    "DecisionExplainer",
]
