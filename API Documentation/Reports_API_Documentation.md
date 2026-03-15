# Reports API Documentation

## Overview

The **Reports** module provides analytical data across seven report types for the BitsOfTrade platform. All endpoints read from the authenticated user's trade log and related models, applying optional date/market/broker filters.

---

## Base URL

```
/api/reports/
```

---

## Authentication

All endpoints require JWT authentication.

```
Authorization: Bearer <access_token>
```

---

## Common Query Parameters

All report endpoints accept the following optional query parameters:

| Parameter | Type   | Description                                              |
|-----------|--------|----------------------------------------------------------|
| `from`    | string | Start date filter — `YYYY-MM-DD`                        |
| `to`      | string | End date filter — `YYYY-MM-DD`                          |
| `market`  | string | Filter by market type. Use `all` or omit to include all |
| `broker`  | string | Filter by broker name (case-insensitive). Use `all` or omit to include all |

> **Note:** The `behavior`, `journal`, and `overview` endpoints use only `from` and `to` for their internal period comparisons. `market` and `broker` still apply to the underlying trade queryset.

---

## Endpoints

### 1. Performance Report

**`GET /api/reports/performance/`**

Returns a comprehensive performance breakdown covering trade metrics, daily stats, strategy effectiveness, symbol analysis, capital usage, and chart series.

**Permissions:** Authenticated

**Empty Response — `200 OK`** *(no trades in range)*:

```json
{ "message": "No trades in the selected range." }
```

**Success Response — `200 OK`:**

```json
{
  "performance": {
    "total_pnl": 4250.00,
    "win_rate": 62.5,
    "profit_factor": 2.1,
    "trade_expectancy": 85.00,
    "avg_trade_pnl": 85.00,
    "total_trades": 50
  },
  "net_pnl_cumulative": [
    { "date": "Jan 2", "pnl": 120.00 },
    { "date": "Jan 3", "pnl": 340.00 }
  ],
  "net_daily_pnl": [
    { "date": "Jan 2", "pnl": 120.00 },
    { "date": "Jan 3", "pnl": 220.00 }
  ],
  "performance_breakdown": {
    "trade_based_metrics": {
      "total_pnl": 4250.00,
      "average_winning_trade": 210.00,
      "average_losing_trade": -95.00,
      "largest_winning_trade": 850.00,
      "largest_losing_trade": -430.00,
      "profit_factor": 2.1,
      "trade_expectancy": 85.00
    },
    "day_based_metrics": {
      "total_trading_days": 22,
      "winning_days": 15,
      "losing_days": 6,
      "breakeven_days": 1,
      "avg_daily_pnl": 193.18,
      "avg_daily_volume": 52000.00,
      "avg_holding_time": "N/A"
    }
  },
  "time_metrics": {
    "trading_days": 22,
    "consecutive_win_days": 5,
    "consecutive_loss_days": 2,
    "most_profitable_day": "Jan 15",
    "least_profitable_day": "Jan 8"
  },
  "duration_insights": {
    "avg_holding_duration": "N/A",
    "best_session": "Late Morning",
    "best_hour": "10:00 AM",
    "most_common_duration": "N/A",
    "trades_count": 50
  },
  "hold_time_vs_win_rate": [],
  "market_session_breakdown": [
    { "session": "Early Morning", "percent_trades": 10 },
    { "session": "Late Morning",  "percent_trades": 45 },
    { "session": "Midday",        "percent_trades": 20 },
    { "session": "Afternoon",     "percent_trades": 15 },
    { "session": "Closing",       "percent_trades": 10 }
  ],
  "strategy_effectiveness": [
    { "strategy": "Breakout", "win_rate": 68.5 },
    { "strategy": "Mean Reversion", "win_rate": 55.0 }
  ],
  "symbol_frequency": {
    "most_traded_symbol": "RELIANCE",
    "most_profitable_symbol": "TCS",
    "least_profitable_symbol": "INFY",
    "highest_win_rate_symbol": "TCS",
    "lowest_win_rate_symbol": "INFY"
  },
  "capital_usage": {
    "max_capital_used": 150000.00,
    "min_capital_used": 12000.00,
    "average_capital_used": 65000.00,
    "pnl_at_max_capital": 850.00,
    "pnl_at_min_capital": -120.00
  },
  "quantity_analysis": {
    "max_quantity": 500,
    "min_quantity": 10,
    "average_quantity": 185.50,
    "pnl_at_max_quantity": 850.00,
    "pnl_at_min_quantity": -50.00
  }
}
```

#### Market Session Definitions

| Session        | Time Range (24h minutes) |
|----------------|--------------------------|
| Early Morning  | 9:15 AM – 11:00 AM       |
| Late Morning   | 11:00 AM – 12:30 PM      |
| Midday         | 12:30 PM – 1:30 PM       |
| Afternoon      | 1:30 PM – 2:30 PM        |
| Closing        | 2:30 PM – 3:31 PM        |

---

### 2. Risk Report

**`GET /api/reports/risk/`**

Returns drawdown analysis, volatility metrics, capital and quantity exposure, risk-adjusted ratios (Sharpe, Sortino), Value at Risk, and R-Multiple statistics.

**Permissions:** Authenticated

> The `risk` endpoint additionally uses `user.trading_capital` as the base capital for percentage calculations. If not set, it falls back to `max_capital_used` from the filtered trades.

**Empty Response — `200 OK`** *(no trades in range)*:

```json
{ "message": "No trades in the selected range." }
```

**Success Response — `200 OK`:**

```json
{
  "max_drawdown": {
    "amount": 3200.00,
    "percentage": 4.27
  },
  "average_drawdown": {
    "amount": 1100.00,
    "percentage": 1.47
  },
  "worst_losing_day": -1250.00,
  "recovery_time": 3,
  "return_volatility": 2.15,
  "drawdown_curve": [
    { "date": "Jan 2", "drawdown": 0.00 },
    { "date": "Jan 3", "drawdown": -320.00 }
  ],
  "max_capital_used": 150000.00,
  "min_capital_used": 12000.00,
  "avg_capital_used": 65000.00,
  "max_quantity": 500,
  "avg_quantity": 185.50,
  "monthly_average_loss": [
    { "month": "Jan", "loss": -420.00 },
    { "month": "Feb", "loss": -310.00 }
  ],
  "risk_statistics": {
    "max_drawdown_pct": -4.3,
    "avg_drawdown_pct": -1.5,
    "largest_losing_day": -1250.00,
    "avg_losing_day": -380.00,
    "avg_realized_r_multiple": 1.8,
    "max_consecutive_losing_days": 3,
    "risk_adjusted_return": 0.42,
    "volatility_index": 2.2
  },
  "risk_exposure_analysis": {
    "value_at_risk_95": 980.00,
    "sharpe_ratio": 1.35,
    "sortino_ratio": 1.92,
    "max_risk_per_trade": 3.5,
    "avg_risk_per_trade": 1.2
  }
}
```

#### Field Notes

| Field | Description |
|-------|-------------|
| `drawdown_curve` | Daily cumulative drawdown series for charting. Values are negative or zero. |
| `recovery_time` | Average number of trading sessions spent recovering from each drawdown |
| `return_volatility` | Annualised standard deviation of daily returns as a percentage |
| `value_at_risk_95` | 95% VaR — worst expected daily loss under normal conditions |
| `avg_realized_r_multiple` | Average P&L expressed as a multiple of per-trade risk (requires `stop_loss` set on trades) |
| `max_risk_per_trade` / `avg_risk_per_trade` | Risk per trade as % of base capital (requires `stop_loss` set on trades) |

---

### 3. Behavior Report

**`GET /api/reports/behavior/`**

Returns discipline KPIs, rule adherence by category, violations timeline, mistake heatmap, and a generated behavior insight string.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "kpis": {
    "DIS": {
      "value": 84.5,
      "trend": "Improving",
      "arrow": "↗"
    },
    "VMI": {
      "value": 22.0,
      "trend": "Low",
      "direction": "Improving",
      "arrow": "↗"
    },
    "DRT": {
      "value": 1.5,
      "trend": "Stable",
      "arrow": "—"
    },
    "ECI": {
      "value": 91.0,
      "trend": "Stable",
      "arrow": "—"
    }
  },
  "snapshot": { },
  "violations_timeline": [
    { "date": "Jan 3", "violations": 2 },
    { "date": "Jan 7", "violations": 1 }
  ],
  "mistake_heatmap": [
    {
      "mistake_type": "Overtrading",
      "occurrences": { "Jan 3": 2, "Jan 8": 1 }
    }
  ],
  "top_recurring_mistakes": [
    { "name": "Overtrading",    "occurrences": 3, "loss_percent": 42.0 },
    { "name": "FOMO Entry",     "occurrences": 1, "loss_percent": 15.0 },
    { "name": "Premature Exit", "occurrences": 0, "loss_percent": 0    },
    { "name": "Missed Stop Loss","occurrences": 0, "loss_percent": 0   },
    { "name": "Revenge Trading","occurrences": 0, "loss_percent": 0    }
  ],
  "behavior_insight": "Mistakes cluster heavily around 'Overtrading', contributing to 42.0% of your mistake-related losses. Review your session triggers before the next trade.",
  "rule_adherence": {
    "Risk Management": 88.0,
    "Entry Rules": 95.0,
    "Exit Rules": 100.0,
    "Position Sizing": 92.0,
    "Time Management": 100.0
  }
}
```

#### KPI Definitions

| KPI   | Full Name                        | Direction | Description |
|-------|----------------------------------|-----------|-------------|
| `DIS` | Discipline Index Score           | Higher is better | Overall discipline score from the metrics snapshot |
| `VMI` | Violation Momentum Index         | Lower is better | Rate/momentum of rule violations; `trend` field holds level (`Low`/`Medium`/`High`), `direction` holds `Improving`/`Stable`/`Declining` |
| `DRT` | Discipline Recovery Time         | Lower is better | Average sessions to recover discipline after a violation cluster |
| `ECI` | Execution Consistency Index      | Higher is better | % of trades in the period with no hard rule violations |

#### Trend / Arrow Values

| Arrow | Meaning   |
|-------|-----------|
| `↗`   | Improving |
| `↘`   | Declining |
| `—`   | Stable    |

#### Rule Adherence Categories

Adherence is expressed as a percentage (0–100). It starts at 100% and decreases based on violation counts relative to total trades in the period.

| Category         | Maps from DB `rule.category` |
|------------------|------------------------------|
| Risk Management  | `risk`                       |
| Entry Rules      | `psychology`                 |
| Exit Rules       | `other` (and any unmapped)   |
| Position Sizing  | `process`                    |
| Time Management  | `time`                       |

#### Default Mistakes

The following mistakes always appear in `top_recurring_mistakes` even with zero occurrences, so the frontend always has at least these five entries:

- Premature Exit
- Overtrading
- FOMO Entry
- Missed Stop Loss
- Revenge Trading

Any admin-defined mistakes are also included.

---

### 4. Strategy Report

**`GET /api/reports/strategy/`**

Returns per-strategy performance breakdown for all strategies used in the filtered trade range.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "strategy_id": 1,
    "strategy_name": "Breakout",
    "total_trades": 30,
    "win_rate": 70.0,
    "total_pnl": 3100.00,
    "profit_factor": 2.4
  },
  {
    "strategy_id": 2,
    "strategy_name": "Mean Reversion",
    "total_trades": 20,
    "win_rate": 50.0,
    "total_pnl": 1150.00,
    "profit_factor": 1.3
  }
]
```

> Results are sorted by `total_pnl` descending. Trades with no strategy assigned are excluded. Strategies whose DB record has been deleted return `"strategy_name": "Unknown"`.

---

### 5. Journal Report

**`GET /api/reports/journal/`**

Returns psychology analysis, mistake summary, trigger analysis, and journal discipline metrics for the filtered period.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "psychology_report": {
    "emotion_frequency": [
      { "emotion": "Calm",    "count": 18 },
      { "emotion": "Anxious", "count": 7  }
    ],
    "confidence_vs_outcome": [
      { "confidence": 8, "pnl": 320.00 },
      { "confidence": 4, "pnl": -150.00 }
    ],
    "most_common_emotion": "Calm",
    "confidence_correlation": 0.61,
    "satisfaction_correlation": 0.48,
    "emotional_impact_pnl": 540.00,
    "avg_confidence": 6.8,
    "avg_satisfaction": 7.1,
    "psychology_insight": "Trades taken while 'Anxious' show 38% lower expectancy than 'Calm' trades. Consider implementing pre-trade routines to stay in a 'Calm' mindset."
  },
  "mistake_report": {
    "mistake_frequency": {
      "Overtrading": 3,
      "FOMO Entry": 1
    },
    "loss_contribution": {
      "Overtrading": 820.00,
      "FOMO Entry": 210.00
    },
    "most_frequent_mistake": "Overtrading",
    "total_mistake_cost": 1030.00,
    "avg_cost_per_mistake": 257.50,
    "clustering_pattern_detected": true
  },
  "trigger_analysis": {
    "Money pressure": { "trades": 5, "avg_pnl": -180.00 },
    "Losing streak":  { "trades": 8, "avg_pnl": -95.00  },
    "Winning streak": { "trades": 12, "avg_pnl": 210.00 }
  },
  "journal_discipline": {
    "completion_rate": 85.7,
    "current_streak": 5,
    "longest_streak": 12,
    "missed_journaling_days": 3,
    "journal_count": 18
  }
}
```

#### Field Notes

| Field | Description |
|-------|-------------|
| `confidence_correlation` | Pearson correlation coefficient (-1 to 1) between pre-trade confidence and trade P&L |
| `satisfaction_correlation` | Pearson correlation between post-trade satisfaction and P&L |
| `emotional_impact_pnl` | Total P&L summed across all emotion states (net impact) |
| `clustering_pattern_detected` | `true` if more than 3 mistakes were logged in the period |
| `trigger_analysis` | Combines `pressure_source` from `PsychologyLog` and streak-based triggers. Keys are human-readable labels. |

#### Trigger Labels

| Raw Value       | Display Label    |
|-----------------|------------------|
| `money`         | Money pressure   |
| `time`          | Time pressure    |
| `missed_move`   | Missed move      |
| `anger`         | Anger            |
| `uncertainty`   | Uncertainty      |
| *(streak ≥ 2)*  | Losing streak / Winning streak |

---

### 6. Mistakes Report

**`GET /api/reports/mistakes/`**

Returns a focused mistake frequency and loss analysis for the filtered trade range.

**Permissions:** Authenticated

**Empty Response — `200 OK`** *(no trades in range)*:

```json
{ "message": "No trades in the selected range." }
```

**Success Response — `200 OK`:**

```json
{
  "mistake_frequency": {
    "Overtrading": 3,
    "FOMO Entry": 1
  },
  "loss_contribution": {
    "Overtrading": 820.00,
    "FOMO Entry": 210.00
  },
  "most_frequent_mistake": "Overtrading",
  "total_mistake_cost": 1030.00,
  "avg_cost_per_mistake": 257.50,
  "clustering_pattern_detected": true,
  "trigger_analysis": {
    "money": { "trades": 5, "total_pnl": -900.00, "avg_pnl": -180.00 },
    "anger": { "trades": 2, "total_pnl": -310.00, "avg_pnl": -155.00 }
  }
}
```

> `clustering_pattern_detected` is `true` when total mistake count across the period exceeds 3. `trigger_analysis` here uses raw `pressure_source` values (not human-readable labels) and includes `total_pnl` alongside `avg_pnl`, unlike the Journal report's trigger analysis.

---

### 7. Overview Report

**`GET /api/reports/overview/`**

Returns a dashboard-level summary combining net P&L cards, win rate comparison, chart series, session health, discipline vs performance breakdown, and exclusive proprietary metrics.

**Permissions:** Authenticated

**Period Logic:**
- If `from` and `to` are provided, compares that custom period against the immediately preceding period of equal length.
- If no dates are provided, auto-detects the most recent month with trades and compares it against the previous calendar month. The comparison label is `"vs last month"` or `"vs previous period"`.

**Success Response — `200 OK`:**

```json
{
  "netPnl": {
    "value": 4250.00,
    "percentChange": 18.5,
    "vsText": "vs last month"
  },
  "tradeWinPercent": {
    "value": 62.5,
    "percentChange": 4.2,
    "vsText": "improvement"
  },
  "profitFactor": 2.1,
  "dayWinPercent": 68.2,
  "avgWin": 210.00,
  "avgLoss": -95.00,
  "chartData": {
    "netPnlCumulative": [
      { "date": "Jan 2", "pnl": 120.00 },
      { "date": "Jan 3", "pnl": 340.00 }
    ],
    "netDailyPnl": [
      { "date": "Jan 2", "pnl": 120.00 },
      { "date": "Jan 3", "pnl": 220.00 }
    ]
  },
  "sessionHealth": {
    "status": "Normal",
    "color": "green",
    "tradesToday": 3,
    "rulesViolated": 0,
    "mistakesLogged": 1,
    "journalCompleted": true
  },
  "disciplineVsPerformance": {
    "disciplined": {
      "winRate": 72.0,
      "avgReturn": 2.1,
      "drawdown": -1.4
    },
    "undisciplined": {
      "winRate": 45.0,
      "avgReturn": -0.8,
      "drawdown": -5.2
    }
  },
  "exclusiveMetrics": {
    "di":  84.5,
    "vmi": "Low",
    "drt": 1.5,
    "tpr": 76.0,
    "fie": 1200.00,
    "ovr": 88.0,
    "eci": 950.00,
    "cas": 91.0,
    "dae": 2.3,
    "smi": "Active",
    "ddr": "Low",
    "cpi": 100.0
  }
}
```

#### Session Health Field Notes

| Field              | Description |
|--------------------|-------------|
| `status`           | `"Normal"` / `"Warning"` / `"Locked"` |
| `color`            | `"green"` / `"yellow"` / `"red"` — current `DisciplineSession` state |
| `tradesToday`      | Number of trades on the active session's date |
| `rulesViolated`    | `violations_count` from the active `DisciplineSession` |
| `mistakesLogged`   | `TradeMistake` count for that session date |
| `journalCompleted` | Whether the daily journal was completed for the session |

#### Discipline vs Performance Field Notes

| Field        | Description |
|--------------|-------------|
| `winRate`    | Win rate % for trades in disciplined / undisciplined sessions |
| `avgReturn`  | Average P&L expressed as a multiple of average loss (R-multiple proxy) |
| `drawdown`   | Max drawdown % relative to `user.trading_capital`. Negative value. |

> **Disciplined** = trades belonging to `DisciplineSession` where `peak_state = "green"`.
> **Undisciplined** = all other sessions.

#### Exclusive Metrics Reference

| Key   | Description |
|-------|-------------|
| `di`  | Discipline Index score |
| `vmi` | Volatility/Violation Momentum Index level (`"Low"` / `"Medium"` / `"High"`) |
| `drt` | Discipline Recovery Time in days |
| `tpr` | Trade Process Rating score |
| `fie` | Financial Impact of Errors (currency amount) |
| `ovr` | Overall score |
| `eci` | Emotional Cost Index (currency amount) |
| `cas` | Consistency Adherence Score |
| `dae` | Daily Average Expectancy (R-multiple) |
| `smi` | Strategy Maturity Index status (e.g. `"Active"`, `"Dev"`) |
| `ddr` | Drawdown Risk level |
| `cpi` | Consistency Performance Index score (defaults to `100.0` if not set) |

---

## URL Configuration

```python
# reports/urls.py
urlpatterns = [
    path('performance/', performance_report_view, name='report-performance'),
    path('risk/',        risk_report_view,         name='report-risk'),
    path('behavior/',    behavior_report_view,     name='report-behavior'),
    path('strategy/',    strategy_report_view,     name='report-strategy'),
    path('journal/',     journal_report_view,      name='report-journal'),
    path('mistakes/',    mistake_report_view,      name='report-mistake'),
    path('overview/',    overview_report_view,     name='report-overview'),
]
```

---

## Internal Architecture

The module is split into focused sub-modules. `services.py` re-exports everything so existing call sites need no changes.

| File             | Responsibility |
|------------------|----------------|
| `views.py`       | API wrappers — applies filters, calls services, returns `Response` |
| `services.py`    | Public re-export facade for all report functions |
| `overview.py`    | Overview dashboard data, period comparison logic |
| `performance.py` | Trade/day metrics, sessions, strategies, symbols |
| `risk.py`        | Drawdown, volatility, Sharpe/Sortino, VaR, R-multiples |
| `behavior.py`    | Discipline KPIs, rule adherence, violation timeline, mistake heatmap |
| `journal.py`     | Psychology correlations, trigger analysis, journal discipline |
| `mistakes.py`    | Mistake frequency, loss contribution, trigger analysis |
| `strategy.py`    | Per-strategy win rate, P&L, profit factor |
| `utils.py`       | Shared helpers: `build_daily_rows`, `build_cumulative_and_daily_series`, `win_rate`, `profit_factor`, `consecutive_streaks`, `fmt_date` |

---

## Error Reference

| Status Code | Meaning                                              |
|-------------|------------------------------------------------------|
| `200`       | OK — data returned (may include `"message"` key if no trades found) |
| `401`       | Unauthorized — missing or invalid JWT token          |
| `405`       | Method Not Allowed — all endpoints are `GET` only    |

---

## Dependencies

- `djangorestframework`
- `tradelog` — `Trade` model (primary data source)
- `discipline` — `DisciplineSession`, `ViolationsLog`
- `mistakes` — `TradeMistake`, `Mistake`
- `journal` — `DailyJournal`, `PsychologyLog`, `SessionRecap`
- `strategies` — `Strategy`
- `insights` — `calculate_metrics`, `MetricsSnapshotSerializer`, `UserMetricSnapshot`
