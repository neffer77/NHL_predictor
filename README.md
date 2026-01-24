# NHL Predictor

Advanced predictive analytics application for NHL game outcome forecasting. Generates daily picks using statistical modeling, contextual analysis, and value-based selection algorithms.

## Features

- **Statistical Power Score (SPS)** - Weighted combination of xGF%, HDCF%, and GSAx metrics
- **Contextual Adjustment Layer** - Accounts for fatigue, travel, injuries, and referee bias
- **Kelly Criterion Integration** - Optimal bet sizing based on edge calculations
- **Bayesian Priors** - Handles early-season small sample sizes
- **PDO Regression Analysis** - Identifies unsustainable performance
- **Automated Data Pipeline** - Fetches from NHL API, Natural Stat Trick, MoneyPuck, and more

## Installation

### Prerequisites

- Python 3.11 or higher
- pip package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/neffer77/NHL_predictor.git
cd NHL_predictor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# For development dependencies
pip install -e ".[dev]"
```

## Usage

### Command Line Interface

```bash
# Generate today's picks
nhl-predict today

# Generate picks for a specific date
nhl-predict date 2026-01-15

# Show system status and data freshness
nhl-predict status

# Show performance history
nhl-predict history --period 30d

# Run historical backtest
nhl-predict backtest 2025-10-15 --end 2025-12-31

# Update data sources
nhl-predict update
```

### Output Formats

```bash
# Console output (default)
nhl-predict today

# JSON output
nhl-predict today --format json

# Markdown output
nhl-predict today --format markdown

# Save to file
nhl-predict today --save
```

### Example Output

```
═══════════════════════════════════════════════════
NHL DAILY PICKS - Friday, January 24, 2026
═══════════════════════════════════════════════════

Model Accuracy: 58.2% (7d) | 55.8% (30d)
Overall: High - Strong edge opportunities

────────────────────────────────────────────────────
PICK #1 - ★★★ LOCK
Toronto Maple Leafs @ Boston Bruins
► PICK: Boston Bruins
► Confidence: 61.2%
► Edge: +5.8% vs Market
► Goalie: Jeremy Swayman (Confirmed)
► Game Time: 19:00
► Risk: LOW
► Rationale: Goalie advantage (Swayman +8.2 GSAx), Toronto on B2B
```

## Project Structure

```
NHL_predictor/
├── src/nhl_predictor/
│   ├── fetchers/           # Data ingestion modules
│   │   ├── nhl_api.py
│   │   ├── natural_stat_trick.py
│   │   ├── moneypuck.py
│   │   ├── daily_faceoff.py
│   │   └── scouting_refs.py
│   ├── features/           # Feature engineering
│   │   ├── xg_aggregator.py
│   │   ├── hdcf_calculator.py
│   │   ├── gsax_calculator.py
│   │   ├── pdo_tracker.py
│   │   ├── schedule_analyzer.py
│   │   └── contextual_adjustments.py
│   ├── prediction/         # Prediction engine
│   │   ├── sps_calculator.py
│   │   ├── contextual_layer.py
│   │   ├── probability_engine.py
│   │   ├── kelly_criterion.py
│   │   └── calibration.py
│   ├── selection/          # Pick selection
│   │   ├── filters.py
│   │   ├── ranking.py
│   │   ├── stability.py
│   │   ├── selector.py
│   │   └── pdo_hunter.py
│   ├── reporting/          # Output generation
│   │   ├── report_generator.py
│   │   ├── rationale.py
│   │   ├── performance.py
│   │   └── notifications.py
│   ├── infrastructure/     # Operations
│   │   ├── scheduler.py
│   │   ├── freshness.py
│   │   ├── backtest.py
│   │   └── resilience.py
│   ├── models/             # Database models
│   │   ├── schema.py
│   │   └── database.py
│   └── utils/              # Utilities
│       └── team_mapping.py
├── tests/                  # Test suite
├── data/                   # SQLite database
├── reports/                # Generated reports
└── logs/                   # Application logs
```

## How It Works

### 1. Statistical Power Score (SPS)

The core metric combining three key indicators:

```
SPS = (0.45 × xGF%) + (0.25 × HDCF%) + (0.30 × GSAx_normalized)
```

- **xGF%** (45%) - Expected Goals For percentage, score-adjusted
- **HDCF%** (25%) - High-Danger Chances For percentage
- **GSAx** (30%) - Goals Saved Above Expected for starting goalie

### 2. Contextual Adjustment Layer (CAL)

Multipliers applied to base SPS:

| Factor | Scalar | Condition |
|--------|--------|-----------|
| Home Ice | 1.04× | Playing at home |
| Back-to-Back | 0.88× | Second game in 2 nights |
| Travel | 0.94× | >2 timezone change |
| Key Injury | 0.90× | Top scorer out |
| Referee Bias | 1.03× | Home-friendly referee |

### 3. Win Probability

Logistic regression converts SPS differential to probability:

```
P(Home Win) = 1 / (1 + e^(-k × SPS_differential))
```

### 4. Edge Calculation

```
Edge = Model_Probability - Market_Implied_Probability
```

Categories:
- **Strong Edge**: > 5%
- **Moderate Edge**: 2-5%
- **Weak Edge**: 0-2%

### 5. Kelly Criterion

Optimal stake sizing based on edge:

```
f* = (b × p - q) / b
```

Where: b = decimal odds - 1, p = model probability, q = 1 - p

Confidence ratings:
- **LOCK**: Kelly > 8%
- **STRONG**: Kelly 5-8%
- **STANDARD**: Kelly 2-5%
- **LEAN**: Kelly 1-2%

### 6. Selection Algorithm

1. Filter out high-risk games (unconfirmed goalies, coin-flip probabilities)
2. Calculate edge for all remaining games
3. Rank by edge with stability as tie-breaker
4. Apply PDO mismatch bonus
5. Select top 4 picks

## Configuration

Create a `config.yaml` file or use environment variables:

```yaml
# config.yaml
database:
  path: "./data/nhl_predictor.db"

model:
  xgf_weight: 0.45
  hdcf_weight: 0.25
  gsax_weight: 0.30
  min_confidence: 0.53
  picks_per_day: 4

schedule:
  predictions_time: "14:00"
  goalie_check_interval: 60

notifications:
  email_enabled: false
  webhook_enabled: false
```

Environment variable overrides:

```bash
export NHL_DB_PATH="./data/nhl.db"
export NHL_LOG_LEVEL="DEBUG"
export NHL_PICKS_PER_DAY=4
export NHL_MIN_CONFIDENCE=0.53
```

## Data Sources

| Source | Data | Update Frequency |
|--------|------|------------------|
| NHL API | Schedule, scores, standings | Daily 8:00 AM |
| Natural Stat Trick | xG, HDCF, Corsi | Daily 9:00 AM |
| MoneyPuck | Simulations, GSAx | Daily 10:00 AM |
| Daily Faceoff | Starting goalies | Hourly 10 AM - 7 PM |
| Scouting The Refs | Referee assignments | Daily 12:00 PM |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=nhl_predictor

# Run specific test file
pytest tests/test_prediction.py

# Run specific test class
pytest tests/test_prediction.py::TestSPSCalculator
```

## Scheduled Jobs

The application can run as a daemon with automated jobs:

```python
from nhl_predictor.infrastructure.scheduler import run_scheduler

# Start scheduler (blocking)
run_scheduler()
```

Default schedule:
- **08:00** - Fetch NHL schedule
- **09:00** - Fetch NST stats
- **10:00** - Fetch MoneyPuck data
- **12:00** - Fetch referee assignments
- **10:00-19:00** - Check goalie status (hourly)
- **14:00** - Generate daily picks
- **23:00** - Update prediction outcomes

## Performance Tracking

The system tracks historical performance:

```bash
# View performance summary
nhl-predict history

# Detailed breakdown
nhl-predict history --detailed

# Specific period
nhl-predict history --period 7d
```

Tracked metrics:
- Win rate by tier (LOCK, STRONG, STANDARD, LEAN)
- ROI (assuming flat betting)
- Brier score for probability calibration
- Win/loss streaks

## Backtesting

Test model changes against historical data:

```bash
# Run backtest
nhl-predict backtest 2025-10-15 --end 2025-12-31 --output results.json
```

Features:
- Point-in-time data handling (no data leakage)
- Multiple configuration comparison
- Tier and monthly performance breakdown

## API Reference

### Core Classes

```python
from nhl_predictor.selection import PickSelector, select_picks
from nhl_predictor.prediction import SPSCalculator, ProbabilityEngine
from nhl_predictor.reporting import ReportGenerator

# Generate picks
picks = select_picks(game_date=date.today(), pick_count=4)

# Access individual picks
for pick in picks.picks:
    print(f"{pick.pick_team}: {pick.model_probability:.1%} ({pick.tier})")
```

### Convenience Functions

```python
from nhl_predictor.prediction import (
    calculate_sps,
    calculate_win_probability,
    calculate_kelly,
    american_to_probability,
)

from nhl_predictor.features import (
    get_team_xg,
    get_goalie_gsax,
    get_schedule_context,
    find_regression_candidates,
)
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - see LICENSE file for details.

## Disclaimer

This application is for educational and entertainment purposes only. Sports betting involves risk, and past performance does not guarantee future results. Always gamble responsibly and within your means.
