"""
reports/services.py

Public API — re-exports every report function so existing call sites
(views, tests, management commands) require zero changes.

Internal code should import directly from the sub-modules, e.g.:
    from reports.performance import get_performance_report_data
"""

from .behavior import get_behavior_report_data
from .journal import get_journal_report_data
from .mistakes import get_mistakes_report_data
from .overview import get_overview_report_data
from .performance import get_performance_report_data
from .risk import get_risk_report_data
from .strategy import get_strategy_report_data

__all__ = [
    "get_performance_report_data",
    "get_risk_report_data",
    "get_behavior_report_data",
    "get_strategy_report_data",
    "get_journal_report_data",
    "get_mistakes_report_data",
    "get_overview_report_data",
]