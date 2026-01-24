# NHL Prediction Application - Epics and User Stories

## Project Overview
Build a predictive analytics application for NHL game outcomes (2025/2026 season) that generates 4 high-confidence daily picks using advanced statistical modeling, contextual analysis, and value-based selection algorithms.

---

## Epic 1: Data Ingestion & Normalization

**Objective:** Build the automated pipeline to fetch, normalize, and store daily data from multiple sources.

### Story 1.1: NHL API Schedule Fetcher
**Description:** Create a Python module using `nhl-api-py` to retrieve the daily game schedule from the NHL Edge API.

**Acceptance Criteria:**
- [ ] Script connects to `https://api-web.nhle.com/v1/schedule/{date}`
- [ ] Returns JSON list containing: GameIDs, Home/Away teams, Start Times, Venue
- [ ] Handles "No Games Scheduled" edge case gracefully
- [ ] Implements retry logic with exponential backoff (3 retries)
- [ ] Scheduled to run at 08:00 AM daily
- [ ] Logs all fetch operations with timestamps

**Technical Notes:**
- Use `nhl-api-py` library as wrapper
- Store raw response for debugging/auditing

---

### Story 1.2: Team Name Normalization ("Golden Record" Mapper)
**Description:** Create a mapping system to normalize team names across all data sources (NST, MoneyPuck, NHL API, Daily Faceoff).

**Acceptance Criteria:**
- [ ] Function `normalize_team_name(raw_name)` returns standard 3-letter code
- [ ] Handles all 32 NHL teams including variations:
  - Full names ("Montreal Canadiens")
  - Short names ("Canadiens", "Habs")
  - Abbreviations ("MTL")
  - Special characters ("Montréal Canadiens")
- [ ] Includes Utah Hockey Club mapping (formerly Arizona Coyotes)
- [ ] Returns original input if no match found (with warning log)
- [ ] Unit tests cover all known variations from each source

**Technical Notes:**
```python
TEAM_MAPPING = {
    "Anaheim Ducks": "ANA", "Ducks": "ANA",
    "Utah Hockey Club": "UTA", "Arizona Coyotes": "UTA",
    # ... all 32 teams
}
```

---

### Story 1.3: Natural Stat Trick (NST) Scraper
**Description:** Build a web scraper to fetch team-level advanced statistics from Natural Stat Trick.

**Acceptance Criteria:**
- [ ] Scrapes 5v5 Score-Adjusted team reports
- [ ] URL construction handles season parameters correctly
- [ ] Extracts key metrics: CF%, xGF%, HDCF%, PDO, SF%, SCF%
- [ ] Uses `pandas.read_html()` for table parsing
- [ ] Implements retry logic on connection timeout (3 retries, exponential backoff)
- [ ] Saves daily snapshot to database with timestamp
- [ ] Handles rate limiting gracefully (minimum 2-second delay between requests)

**Technical Notes:**
- Target URL: `https://www.naturalstattrick.com/teamtable.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&rate=n&team=all&loc=B&gpf=410`
- Parameters: `sit=5v5`, `stype=2` (Regular Season)

---

### Story 1.4: MoneyPuck Data Fetcher
**Description:** Implement automated download and parsing of MoneyPuck's daily CSV data dumps.

**Acceptance Criteria:**
- [ ] Downloads `moneypuck.com/moneypuck/simulations/simulations_recent.csv`
- [ ] Parses CSV into structured DataFrame
- [ ] Extracts: Win Probability, Power Rankings, Flurry-Adjusted xG
- [ ] Handles file not found / server unavailable errors
- [ ] Stores parsed data with date stamp
- [ ] Scheduled to run at 10:00 AM daily

---

### Story 1.5: Daily Faceoff Goalie Scraper
**Description:** Build scraper to fetch confirmed starting goaltenders from Daily Faceoff.

**Acceptance Criteria:**
- [ ] Scrapes `dailyfaceoff.com/starting-goalies`
- [ ] Identifies goalie confirmation status: "Confirmed", "Expected", "Unconfirmed"
- [ ] Extracts goalie name, team, and opponent
- [ ] Uses BeautifulSoup for HTML parsing
- [ ] Updates hourly during pre-game window (10 AM - 7 PM)
- [ ] Triggers alert/flag when starter changes from previous check

**Technical Notes:**
- Critical for GSAx calculations
- Unconfirmed goalies require weighted tandem average

---

### Story 1.6: Scouting The Refs Scraper
**Description:** Implement scraper for daily referee assignments and historical bias statistics.

**Acceptance Criteria:**
- [ ] Scrapes `scoutingtherefs.com` for daily assignments
- [ ] Extracts: Referee names, assigned games
- [ ] Fetches referee statistics: Home Win %, Penalties/Game, Career games
- [ ] Calculates deviation from league average for each stat
- [ ] Scheduled to run at 12:00 PM daily
- [ ] Stores referee profiles in database for historical analysis

---

### Story 1.7: NHL Standings & Form Fetcher
**Description:** Retrieve current standings and recent form data from NHL API.

**Acceptance Criteria:**
- [ ] Connects to `https://api-web.nhle.com/v1/standings/now`
- [ ] Extracts: Points, L10 Record, Home/Away splits, Streak
- [ ] Calculates "Points Pace" (projected season total)
- [ ] Identifies playoff position / bubble status
- [ ] Updates daily after games complete

---

### Story 1.8: Database Schema Implementation
**Description:** Design and implement SQLite database schema for storing all collected data.

**Acceptance Criteria:**
- [ ] Creates `games` table: game_id (PK), date, home_team, away_team, home_score, away_score, winner
- [ ] Creates `team_daily_stats` table: date, team_id, xg_share, hdcf_share, pdo, cf_share, rest_days
- [ ] Creates `goalie_stats` table: date, player_id, gsax, shots_faced, goals_allowed, save_pct
- [ ] Creates `predictions` table: game_id, model_prob_home, implied_prob_home, edge, pick_status
- [ ] Creates `referees` table: ref_id, name, home_win_pct, penalties_per_game, games_officiated
- [ ] Implements proper indexes for query performance
- [ ] Includes data migration/versioning support

---

## Epic 2: Feature Engineering & Context Engine

**Objective:** Transform raw data into predictive features including statistical metrics and contextual adjustments.

### Story 2.1: Expected Goals (xG) Aggregator
**Description:** Implement system to aggregate and process Expected Goals data at team level.

**Acceptance Criteria:**
- [ ] Calculates rolling xGF% (Expected Goals For percentage) - 10, 20, full season windows
- [ ] Uses Score-Adjusted xG to normalize for game state effects
- [ ] Integrates "Flurry-Adjusted" xG from MoneyPuck when available
- [ ] Separates 5v5, Power Play, and Penalty Kill xG
- [ ] Stores historical xG trends for regression analysis

**Technical Notes:**
- xGF% = xGF / (xGF + xGA) * 100
- Score adjustment accounts for teams playing differently when ahead/behind

---

### Story 2.2: High-Danger Chances Calculator
**Description:** Process and aggregate High-Danger Chance metrics (HDCF%).

**Acceptance Criteria:**
- [ ] Calculates HDCF% from NST data
- [ ] Computes rolling averages (10-game, 20-game, season)
- [ ] Identifies "Counter-Attack" team profile (Low Corsi / High HDCF)
- [ ] Flags teams with significant HDCF vs CF divergence
- [ ] Weights HDCF at 0.25 in Statistical Power Score

---

### Story 2.3: Rolling GSAx Calculator
**Description:** Implement logic to calculate rolling Goals Saved Above Expected for goaltenders.

**Acceptance Criteria:**
- [ ] Stores game-by-game GSAx for every goalie
- [ ] Calculates 10-game rolling GSAx sum
- [ ] Calculates 20-game and season GSAx
- [ ] Query returns rolling GSAx for confirmed starter
- [ ] Identifies "hot" (GSAx > +3 last 10) and "cold" (GSAx < -3) streaks
- [ ] Calculates "Backup Penalty" differential (Starter GSAx - Backup GSAx)

**Technical Notes:**
- GSAx = Expected Goals Against - Actual Goals Against
- Positive = goalie performing above average
- Use MoneyPuck or Evolving Hockey as GSAx source

---

### Story 2.4: PDO Regression Tracker
**Description:** Calculate and track PDO (luck metric) for regression-to-mean analysis.

**Acceptance Criteria:**
- [ ] Calculates PDO = (Shooting % + Save %) * 1000
- [ ] Tracks rolling 10-game PDO
- [ ] Flags "Hot" teams (PDO > 1040) as regression candidates
- [ ] Flags "Cold" teams (PDO < 960) as bounce-back candidates
- [ ] Generates "PDO Mismatch" alerts when high-PDO plays low-PDO team

**Technical Notes:**
- League average PDO = 1000 (always)
- PDO deviation > 40 points strongly indicates regression

---

### Story 2.5: Fatigue & Schedule Analyzer
**Description:** Algorithm to analyze schedule factors including rest days, travel, and game density.

**Acceptance Criteria:**
- [ ] Identifies Back-to-Back (B2B) scenarios (0 days rest)
- [ ] Calculates "3-in-4" severity (3 games in 4 nights)
- [ ] Detects "4-in-6" stretches
- [ ] Flags "First Game Home After Long Road Trip" (>4 away games)
- [ ] Compares rest advantage: (Team A Rest Days) - (Team B Rest Days)
- [ ] Applies fatigue scalar 0.88 (12% reduction) for B2B scenarios

**Technical Notes:**
- Check previous game date and location for both teams
- Consider travel distance/time zones

---

### Story 2.6: Travel & Circadian Rhythm Calculator
**Description:** Quantify circadian disruption impact based on time zone changes and game start times.

**Acceptance Criteria:**
- [ ] Maps each team's home time zone
- [ ] Calculates time zone differential for away teams
- [ ] Identifies "body clock" game times (e.g., 7 PM EST = 4 PM PST)
- [ ] Flags games starting before 5 PM local body time
- [ ] Applies travel scalar 0.94 for >2 time zone change
- [ ] Identifies "Scheduled Loss" scenarios (B2B + Road + vs Rested Home)

---

### Story 2.7: Referee Bias Integrator
**Description:** Process referee assignment data and calculate bias adjustments.

**Acceptance Criteria:**
- [ ] Merges referee assignments with daily game schedule
- [ ] Calculates referee's historical Home Win % deviation from league average
- [ ] Calculates referee's Penalties/Game vs league average
- [ ] Returns bias tag: "Neutral", "Home Friendly", "Away Friendly"
- [ ] Adjusts home team probability by 1.03x if ref Home Bias > 5% above average
- [ ] Identifies high-event referees for PP-dominant team matchups

---

### Story 2.8: Power Play Efficiency Analyzer
**Description:** Calculate expected vs actual power play performance for breakout prediction.

**Acceptance Criteria:**
- [ ] Tracks PP% (actual conversion rate)
- [ ] Calculates xG/60 on Power Play (expected efficiency)
- [ ] Identifies teams with low PP% but high PP xG/60 (due for breakout)
- [ ] Identifies teams with high PP% but low PP xG/60 (due for regression)
- [ ] Flags matchups where PP-strong team faces high-penalty referee

---

### Story 2.9: Injury & Lineup Impact Assessor
**Description:** Track key player injuries and calculate lineup impact on win probability.

**Acceptance Criteria:**
- [ ] Integrates injury data from Daily Faceoff / NHL API
- [ ] Identifies "Top Scorer OUT" scenarios
- [ ] Calculates team's dependence on top line (% of scoring)
- [ ] Applies injury scalar 0.90 when MVP-level player is OUT
- [ ] Flags "Top-Heavy" away teams (>40% scoring from one line)
- [ ] Adjusts for announced lineup changes <2 hours before game

---

### Story 2.10: Shooting Talent Adjustment
**Description:** Incorporate individual shooter talent into xG calculations.

**Acceptance Criteria:**
- [ ] Identifies elite shooters (e.g., Matthews, Bedard, Ovechkin)
- [ ] Calculates "Shooting Talent Above Average" per player
- [ ] Adjusts team xG based on shooter quality in projected lineup
- [ ] Higher weight in "Low Event" game matchups
- [ ] Sources data from MoneyPuck's talent-adjusted models

---

### Story 2.11: Coach System Classifier
**Description:** Classify coaching systems and their impact on game flow.

**Acceptance Criteria:**
- [ ] Identifies "Low Event" systems (suppress both xGF and xGA)
- [ ] Identifies "High Event" systems (aggressive, high-risk)
- [ ] Calculates Combined xG/60 expectation for matchups
- [ ] Flags Low Event matchups (< 4.5 Combined xG/60) for special handling
- [ ] Increases Shooting Talent weight in Low Event games

---

### Story 2.12: Desperation/Standings Effect Calculator
**Description:** Calculate playoff race impact on team behavior (late season).

**Acceptance Criteria:**
- [ ] Activates after March 1st (configurable date)
- [ ] Calculates points differential from playoff cutoff line
- [ ] Identifies "Desperation" teams (2-4 points out)
- [ ] Identifies "Eliminated" teams (mathematically out)
- [ ] Identifies "Clinched" teams (playoff spot secured)
- [ ] Adjusts xG projections for desperation factor (higher effort + higher risk)

---

## Epic 3: Modeling & Prediction Engine

**Objective:** Build the core prediction algorithms including probability calculation and value analysis.

### Story 3.1: Statistical Power Score (SPS) Calculator
**Description:** Implement the weighted formula to calculate raw team strength scores.

**Acceptance Criteria:**
- [ ] Calculates SPS (0-100 scale) using formula:
  ```
  SPS = (W1 × xGF%) + (W2 × HDCF%) + (W3 × GSAx_normalized)
  ```
- [ ] Default weights: W1=0.45, W2=0.25, W3=0.30
- [ ] Accepts configurable weights for tuning
- [ ] Calculates SPS for both teams in matchup
- [ ] Returns differential: Home_SPS - Away_SPS

---

### Story 3.2: Contextual Adjustment Layer (CAL)
**Description:** Apply multipliers to base SPS based on game theory variables.

**Acceptance Criteria:**
- [ ] Applies Fatigue Penalty: B2B = 0.88 scalar
- [ ] Applies Travel Penalty: >2 timezone change = 0.94 scalar
- [ ] Applies Referee Adjustment: Home Bias >5% = 1.03 scalar to home team
- [ ] Applies Injury Factor: Top Scorer OUT = 0.90 scalar
- [ ] Applies Home Ice Advantage: Base 1.04 scalar (adjustable)
- [ ] Multipliers stack multiplicatively
- [ ] Returns Adjusted SPS for both teams

---

### Story 3.3: Win Probability Calculator
**Description:** Convert adjusted team scores into win probability percentages.

**Acceptance Criteria:**
- [ ] Takes feature vectors (SPS, CAL adjustments) as input
- [ ] Applies logistic regression function to convert to probability
- [ ] Returns Win % (0.0 to 1.0) for both Home and Away teams
- [ ] Probabilities sum to 1.0 (no draw in NHL regulation + OT/SO)
- [ ] Includes confidence interval based on input data quality

**Technical Notes:**
```
P(Home Win) = 1 / (1 + e^(-k × (Home_Adj_SPS - Away_Adj_SPS)))
```
Where k is trained coefficient

---

### Story 3.4: Market Odds Integrator
**Description:** Fetch and convert betting market odds to implied probabilities.

**Acceptance Criteria:**
- [ ] Retrieves odds from MoneyPuck or odds aggregator
- [ ] Converts American odds to implied probability
- [ ] Converts decimal odds to implied probability
- [ ] Removes vig/juice to get "true" implied probability
- [ ] Stores historical odds for model validation

**Technical Notes:**
- Implied Prob (American +) = 100 / (Odds + 100)
- Implied Prob (American -) = |Odds| / (|Odds| + 100)

---

### Story 3.5: Edge Calculator
**Description:** Calculate the value edge between model probability and market odds.

**Acceptance Criteria:**
- [ ] Calculates Edge = Model_Probability - Market_Implied_Probability
- [ ] Positive edge = value bet, negative edge = market overvalued
- [ ] Categorizes edge magnitude:
  - Strong Edge: > 5%
  - Moderate Edge: 2-5%
  - Weak Edge: 0-2%
  - Negative Edge: < 0%
- [ ] Flags "trap" games (high model prob but negative edge)

---

### Story 3.6: Kelly Criterion Integration
**Description:** Implement Kelly Criterion for confidence/sizing recommendations.

**Acceptance Criteria:**
- [ ] Implements Kelly formula:
  ```
  f* = (b × p - q) / b
  ```
  Where b = decimal odds - 1, p = model prob, q = 1 - p
- [ ] Returns Strength of Pick based on Kelly score:
  - "Lock" / Top Pick: f* > 0.05
  - Standard Pick: f* 0.01 - 0.05
  - Pass: f* <= 0
- [ ] Optional fractional Kelly (0.25x, 0.5x) for conservative sizing
- [ ] Never recommends negative Kelly (pass instead)

---

### Story 3.7: Bayesian Prior for Early Season
**Description:** Implement Bayesian weighting for small sample size handling.

**Acceptance Criteria:**
- [ ] First 20 games: Weight last season data at 50%
- [ ] Games 21-40: Gradually reduce prior weight (40% → 20%)
- [ ] After 40 games: Use current season data only
- [ ] Regresses last season data toward league mean before use
- [ ] Prevents overreaction to early season hot/cold streaks

---

### Story 3.8: Model Calibration Module
**Description:** Track and calibrate model accuracy over time.

**Acceptance Criteria:**
- [ ] Logs all predictions vs actual outcomes
- [ ] Calculates rolling accuracy (10-day, 30-day, season)
- [ ] Calculates Brier Score for probability calibration
- [ ] Identifies systematic biases (e.g., overvaluing home teams)
- [ ] Generates calibration curve visualization
- [ ] Allows weight adjustment based on performance feedback

---

## Epic 4: Selection & Ranking Engine

**Objective:** Implement the "Top 4" selection algorithm to identify the best daily picks.

### Story 4.1: Stay Away Filter
**Description:** Implement filtering logic to remove high-risk/low-value games.

**Acceptance Criteria:**
- [ ] Removes games where starting goalie is "Unconfirmed"
- [ ] Removes games with extreme rest disadvantage AND heavy favorite (no value)
- [ ] Removes games with key injury announced < 2 hours ago (unsettled market)
- [ ] Removes games with Model Probability < 53% (coin flip territory)
- [ ] Flags but doesn't remove early season games (< 15 games played)
- [ ] Logs all filtered games with reason

---

### Story 4.2: Edge-Based Ranking
**Description:** Sort remaining games by calculated edge value.

**Acceptance Criteria:**
- [ ] Calculates Edge for all non-filtered games
- [ ] Sorts games by Edge in descending order
- [ ] Handles ties by secondary sort (Model Probability)
- [ ] Generates ranked list with edge, probability, and odds

---

### Story 4.3: Stability/Variance Check
**Description:** Implement variance analysis as tie-breaker for similar-edge games.

**Acceptance Criteria:**
- [ ] Calculates Stability Score:
  ```
  Stability = (Home_GSAx + Away_GSAx) - (Home_PDO_Variance + Away_PDO_Variance)
  ```
- [ ] Higher stability = more predictable outcome
- [ ] Uses stability as tie-breaker when edges within 0.5%
- [ ] Flags high-variance games (both goalies negative GSAx, high PDO teams)

---

### Story 4.4: Top 4 Selection Algorithm
**Description:** Final selection logic to output exactly 4 picks.

**Acceptance Criteria:**
- [ ] Selects top 4 games by Edge after filtering and stability check
- [ ] If fewer than 4 games have positive edge:
  - Fill remaining slots with highest raw Model_Probability picks
  - Label these as "Low Value / High Confidence"
- [ ] If fewer than 4 total games on schedule: Return all games with picks
- [ ] Never selects same team twice in one day (rare scenario)
- [ ] Returns structured output with pick details

---

### Story 4.5: PDO Mismatch Hunter
**Description:** Specifically identify high-value PDO regression matchups.

**Acceptance Criteria:**
- [ ] Identifies games where Low PDO team (< 980) plays High PDO team (> 1020)
- [ ] Calculates "regression edge" for these matchups
- [ ] Adds bonus weight to edge calculation for PDO mismatches
- [ ] Tracks PDO mismatch pick performance separately

---

## Epic 5: Reporting & User Interface

**Objective:** Deliver the daily picks in a clear, actionable format.

### Story 5.1: Daily Report Generator
**Description:** Create formatted output for the 4 daily picks.

**Acceptance Criteria:**
- [ ] Output includes for each pick:
  - Matchup (Away @ Home)
  - Pick (team to win)
  - Model Confidence %
  - Edge vs Market %
  - Key Rationale (1-2 sentences)
  - Risk Level (Low/Medium/High)
  - Game Start Time
- [ ] Summary section with overall confidence level
- [ ] Outputs to console, JSON file, and optional email

**Example Output:**
```
═══════════════════════════════════════════════════
NHL DAILY PICKS - January 24, 2026
═══════════════════════════════════════════════════

PICK #1 - STRONG EDGE
Toronto Maple Leafs @ Boston Bruins
► PICK: Boston Bruins
► Confidence: 61.2%
► Edge: +5.8% vs Market
► Rationale: Goalie mismatch (Swayman +8.2 GSAx vs Stolarz -2.1),
   Toronto on B2B after West Coast trip
► Risk: LOW

[... picks 2-4 ...]
```

---

### Story 5.2: Rationale Generator
**Description:** Auto-generate human-readable explanations for each pick.

**Acceptance Criteria:**
- [ ] Templates for common scenarios:
  - "Goalie Mismatch" (GSAx differential > 5)
  - "Schedule Spot" (B2B, travel, rest advantage)
  - "PDO Regression" (buying low/selling high)
  - "System Mismatch" (Low Event vs High Event)
  - "Desperation Factor" (playoff race)
- [ ] Combines multiple factors when applicable
- [ ] Prioritizes most impactful factor in lead sentence
- [ ] Maximum 2 sentences per pick

---

### Story 5.3: Historical Performance Tracker
**Description:** Track and display model performance over time.

**Acceptance Criteria:**
- [ ] Records: Pick, Actual Result, Correct/Incorrect, Edge at pick time
- [ ] Calculates: Win Rate, ROI (if tracking units), Brier Score
- [ ] Displays rolling performance (7-day, 30-day, season)
- [ ] Breaks down by pick confidence tier
- [ ] Generates weekly performance summary

---

### Story 5.4: Command Line Interface
**Description:** Create CLI for running predictions and viewing reports.

**Acceptance Criteria:**
- [ ] Commands:
  - `nhl-predict today` - Generate today's picks
  - `nhl-predict date YYYY-MM-DD` - Generate picks for specific date
  - `nhl-predict status` - Show data freshness and system status
  - `nhl-predict history` - Show performance history
  - `nhl-predict backtest` - Run historical backtest
- [ ] Supports JSON output flag for integration
- [ ] Colored output for confidence levels
- [ ] Help documentation for all commands

---

### Story 5.5: Alert/Notification System
**Description:** Send notifications for critical events and daily picks.

**Acceptance Criteria:**
- [ ] Sends daily picks at configurable time (default 2 PM)
- [ ] Alerts when goalie status changes to Confirmed
- [ ] Alerts when late injury affects a picked game
- [ ] Supports email and/or webhook (Slack, Discord) output
- [ ] Configurable notification preferences

---

### Story 5.6: Web Dashboard (Optional/Future)
**Description:** Create simple web interface for viewing picks and performance.

**Acceptance Criteria:**
- [ ] Displays today's picks with full details
- [ ] Shows performance charts and graphs
- [ ] Calendar view of historical picks
- [ ] Mobile-responsive design
- [ ] Optional: User accounts for personalized tracking

---

## Epic 6: Infrastructure & Operations

**Objective:** Ensure reliable operation, scheduling, and maintainability.

### Story 6.1: Scheduled Job Orchestrator
**Description:** Implement scheduling for all data fetching and prediction jobs.

**Acceptance Criteria:**
- [ ] Schedule (all times local):
  - 08:00 AM: NHL API Schedule Fetch
  - 09:00 AM: NST Stats Scrape
  - 10:00 AM: MoneyPuck Data Fetch
  - 12:00 PM: Referee Assignments Fetch
  - 10 AM - 7 PM (hourly): Goalie Status Check
  - 2:00 PM: Generate Daily Picks
- [ ] Uses cron or scheduler library (APScheduler)
- [ ] Handles job failures with retry and alerting
- [ ] Logs all job executions

---

### Story 6.2: Data Freshness Monitor
**Description:** Track and alert on data staleness issues.

**Acceptance Criteria:**
- [ ] Tracks last successful fetch for each data source
- [ ] Alerts if any source is > 24 hours stale
- [ ] Degrades gracefully if source unavailable (use cached data)
- [ ] Status endpoint/command shows all source freshness
- [ ] Adjusts model confidence when using stale data

---

### Story 6.3: Logging & Monitoring System
**Description:** Implement comprehensive logging for debugging and auditing.

**Acceptance Criteria:**
- [ ] Structured logging (JSON format option)
- [ ] Log levels: DEBUG, INFO, WARNING, ERROR
- [ ] Separate log files for: fetchers, model, predictions
- [ ] Log rotation (daily, keep 30 days)
- [ ] Error aggregation and alerting

---

### Story 6.4: Configuration Management
**Description:** Externalize all configurable parameters.

**Acceptance Criteria:**
- [ ] Config file (YAML or JSON) for:
  - Model weights (W1, W2, W3)
  - Adjustment scalars (fatigue, travel, etc.)
  - Data source URLs
  - Notification settings
  - Schedule times
- [ ] Environment variable overrides
- [ ] Validation on startup
- [ ] Hot reload capability for non-critical settings

---

### Story 6.5: Backtesting Framework
**Description:** Enable historical backtesting of model changes.

**Acceptance Criteria:**
- [ ] Loads historical data from database
- [ ] Runs model against historical games with point-in-time data
- [ ] Calculates performance metrics (accuracy, ROI, Brier)
- [ ] Compares multiple model configurations
- [ ] Generates backtest report with visualizations
- [ ] Prevents data leakage (no future data in predictions)

---

### Story 6.6: Error Recovery & Resilience
**Description:** Ensure system handles failures gracefully.

**Acceptance Criteria:**
- [ ] Retry logic for all network operations (exponential backoff)
- [ ] Circuit breaker pattern for repeated failures
- [ ] Fallback to cached data when live fetch fails
- [ ] Transaction rollback on database errors
- [ ] Graceful degradation (partial predictions vs complete failure)

---

## Epic 7: Testing & Quality Assurance

**Objective:** Ensure code quality and prediction accuracy through comprehensive testing.

### Story 7.1: Unit Test Suite
**Description:** Create unit tests for all core modules.

**Acceptance Criteria:**
- [ ] Tests for team name normalization (all variants)
- [ ] Tests for SPS calculation with known inputs
- [ ] Tests for CAL adjustment application
- [ ] Tests for probability conversion
- [ ] Tests for Kelly criterion calculations
- [ ] Minimum 80% code coverage
- [ ] Tests run in CI pipeline

---

### Story 7.2: Integration Test Suite
**Description:** Create integration tests for data pipeline.

**Acceptance Criteria:**
- [ ] Tests actual API connectivity (with mocking option)
- [ ] Tests scraper parsing against known HTML snapshots
- [ ] Tests database read/write operations
- [ ] Tests full prediction pipeline end-to-end
- [ ] Uses test database (not production)

---

### Story 7.3: Data Validation Suite
**Description:** Validate incoming data quality and consistency.

**Acceptance Criteria:**
- [ ] Validates team names resolve to known codes
- [ ] Validates numeric fields are in expected ranges
- [ ] Validates dates are parseable and reasonable
- [ ] Validates no duplicate records
- [ ] Alerts on validation failures

---

### Story 7.4: Model Validation Tests
**Description:** Validate model produces reasonable outputs.

**Acceptance Criteria:**
- [ ] Probabilities always between 0 and 1
- [ ] Home/Away probabilities sum to 1.0
- [ ] No NaN or infinite values
- [ ] Model handles edge cases (missing data, first game of season)
- [ ] Output stability (same inputs = same outputs)

---

## Story Dependencies & Implementation Order

### Phase 1: Foundation (Weeks 1-2)
1. Story 1.8 (Database Schema) - Required first
2. Story 1.2 (Team Normalization) - Needed by all scrapers
3. Stories 1.1, 1.3, 1.4, 1.5, 1.6, 1.7 (Data Fetchers) - Can parallelize

### Phase 2: Feature Engineering (Weeks 3-4)
4. Stories 2.1-2.4 (Core Stats: xG, HDCF, GSAx, PDO)
5. Stories 2.5-2.7 (Context: Fatigue, Travel, Refs)
6. Stories 2.8-2.12 (Advanced: PP, Injuries, Systems)

### Phase 3: Modeling (Weeks 5-6)
7. Stories 3.1-3.3 (Core Model: SPS, CAL, Probability)
8. Stories 3.4-3.6 (Value Analysis: Odds, Edge, Kelly)
9. Stories 3.7-3.8 (Calibration: Bayesian, Monitoring)

### Phase 4: Selection & Output (Weeks 7-8)
10. Stories 4.1-4.5 (Selection Algorithm)
11. Stories 5.1-5.4 (Reporting & CLI)

### Phase 5: Operations & Polish (Weeks 9-10)
12. Stories 6.1-6.6 (Infrastructure)
13. Stories 7.1-7.4 (Testing)
14. Story 5.5-5.6 (Notifications, Dashboard - Optional)

---

## Technical Stack Recommendations

### Core Language
- **Python 3.11+** - Primary development language

### Data & ML Libraries
- `pandas` - Data manipulation
- `numpy` - Numerical operations
- `scikit-learn` - Logistic regression, model evaluation
- `sqlite3` - Database (built-in)

### Web Scraping
- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing
- `pandas.read_html()` - Table extraction

### NHL-Specific
- `nhl-api-py` - NHL API wrapper

### Scheduling & Async
- `APScheduler` - Job scheduling
- `aiohttp` - Async HTTP (optional, for parallel fetching)

### CLI & Output
- `click` or `typer` - CLI framework
- `rich` - Terminal formatting

### Testing
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting

---

## Definition of Done (All Stories)

- [ ] Code implemented and working
- [ ] Unit tests written and passing
- [ ] Code reviewed (if team)
- [ ] Documentation updated
- [ ] Logging implemented
- [ ] Error handling in place
- [ ] Merged to development branch
