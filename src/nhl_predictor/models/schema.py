"""Database schema definitions using SQLAlchemy ORM."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Game(Base):
    """NHL game records."""

    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, unique=True, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    season = Column(String(8), nullable=False)  # e.g., "20252026"
    game_type = Column(Integer, nullable=False)  # 2 = Regular Season, 3 = Playoffs
    home_team = Column(String(3), nullable=False, index=True)
    away_team = Column(String(3), nullable=False, index=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    winner = Column(String(3), nullable=True)
    overtime = Column(Boolean, default=False)
    shootout = Column(Boolean, default=False)
    venue = Column(String(100), nullable=True)
    start_time = Column(DateTime, nullable=True)
    game_state = Column(String(20), default="scheduled")  # scheduled, live, final
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    predictions = relationship("Prediction", back_populates="game")

    __table_args__ = (
        Index("ix_games_date_teams", "date", "home_team", "away_team"),
    )

    def __repr__(self):
        return f"<Game {self.game_id}: {self.away_team} @ {self.home_team} ({self.date})>"


class TeamDailyStats(Base):
    """Daily team statistics snapshot."""

    __tablename__ = "team_daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    team = Column(String(3), nullable=False, index=True)

    # Possession metrics
    cf_pct = Column(Float, nullable=True)  # Corsi For %
    ff_pct = Column(Float, nullable=True)  # Fenwick For %
    sf_pct = Column(Float, nullable=True)  # Shots For %

    # Expected Goals
    xgf = Column(Float, nullable=True)  # Expected Goals For
    xga = Column(Float, nullable=True)  # Expected Goals Against
    xgf_pct = Column(Float, nullable=True)  # Expected Goals For %

    # High Danger Chances
    hdcf = Column(Float, nullable=True)  # High Danger Chances For
    hdca = Column(Float, nullable=True)  # High Danger Chances Against
    hdcf_pct = Column(Float, nullable=True)  # High Danger Chances For %

    # Scoring Chances
    scf = Column(Float, nullable=True)  # Scoring Chances For
    sca = Column(Float, nullable=True)  # Scoring Chances Against
    scf_pct = Column(Float, nullable=True)  # Scoring Chances For %

    # PDO (Luck metric)
    pdo = Column(Float, nullable=True)
    shooting_pct = Column(Float, nullable=True)
    save_pct = Column(Float, nullable=True)

    # Power Play / Penalty Kill
    pp_pct = Column(Float, nullable=True)
    pk_pct = Column(Float, nullable=True)
    pp_xg_per_60 = Column(Float, nullable=True)

    # Record
    games_played = Column(Integer, nullable=True)
    wins = Column(Integer, nullable=True)
    losses = Column(Integer, nullable=True)
    ot_losses = Column(Integer, nullable=True)
    points = Column(Integer, nullable=True)

    # Rest/Schedule
    rest_days = Column(Integer, nullable=True)
    games_last_7 = Column(Integer, nullable=True)

    # Source tracking
    source = Column(String(50), nullable=True)  # e.g., "nst", "moneypuck"
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "team", "source", name="uq_team_daily_stats"),
        Index("ix_team_stats_team_date", "team", "date"),
    )

    def __repr__(self):
        return f"<TeamDailyStats {self.team} ({self.date})>"


class GoalieStats(Base):
    """Goaltender statistics by game or rolling period."""

    __tablename__ = "goalie_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    player_id = Column(Integer, nullable=True, index=True)
    player_name = Column(String(100), nullable=False)
    team = Column(String(3), nullable=False, index=True)

    # Game-level stats
    game_id = Column(Integer, nullable=True)
    shots_against = Column(Integer, nullable=True)
    goals_against = Column(Integer, nullable=True)
    saves = Column(Integer, nullable=True)
    save_pct = Column(Float, nullable=True)

    # Expected Goals metrics
    xga = Column(Float, nullable=True)  # Expected Goals Against
    gsax = Column(Float, nullable=True)  # Goals Saved Above Expected

    # Rolling stats (calculated)
    gsax_rolling_10 = Column(Float, nullable=True)
    gsax_rolling_20 = Column(Float, nullable=True)
    gsax_season = Column(Float, nullable=True)

    # Status
    is_starter = Column(Boolean, default=False)
    confirmation_status = Column(String(20), nullable=True)  # confirmed, expected, unconfirmed

    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_goalie_stats_player_date", "player_name", "date"),
    )

    def __repr__(self):
        return f"<GoalieStats {self.player_name} ({self.date})>"


class Prediction(Base):
    """Model predictions for games."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False, index=True)
    prediction_date = Column(DateTime, default=datetime.utcnow)

    # Model outputs
    home_win_prob = Column(Float, nullable=False)
    away_win_prob = Column(Float, nullable=False)

    # Market comparison
    home_implied_prob = Column(Float, nullable=True)
    away_implied_prob = Column(Float, nullable=True)
    home_edge = Column(Float, nullable=True)
    away_edge = Column(Float, nullable=True)

    # Scores
    home_sps = Column(Float, nullable=True)  # Statistical Power Score
    away_sps = Column(Float, nullable=True)
    home_adjusted_sps = Column(Float, nullable=True)  # After CAL adjustments
    away_adjusted_sps = Column(Float, nullable=True)

    # Selection
    pick = Column(String(3), nullable=True)  # Team code of picked team
    pick_confidence = Column(Float, nullable=True)
    pick_status = Column(String(20), nullable=True)  # top4, pass, low_value
    kelly_score = Column(Float, nullable=True)

    # Rationale
    rationale = Column(Text, nullable=True)
    risk_level = Column(String(10), nullable=True)  # low, medium, high

    # Outcome tracking
    actual_winner = Column(String(3), nullable=True)
    pick_correct = Column(Boolean, nullable=True)

    # Relationships
    game = relationship("Game", back_populates="predictions")

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Prediction Game {self.game_id}: {self.pick} ({self.pick_confidence:.1%})>"


class Referee(Base):
    """Referee profiles and statistics."""

    __tablename__ = "referees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)

    # Career stats
    games_officiated = Column(Integer, nullable=True)
    home_win_pct = Column(Float, nullable=True)
    penalties_per_game = Column(Float, nullable=True)

    # Bias metrics (deviation from league average)
    home_bias = Column(Float, nullable=True)  # positive = favors home
    penalty_deviation = Column(Float, nullable=True)  # positive = more penalties

    # Classification
    bias_tag = Column(String(20), nullable=True)  # neutral, home_friendly, away_friendly
    event_level = Column(String(20), nullable=True)  # low, average, high (penalty frequency)

    last_updated = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Referee {self.name}>"


class RefereeAssignment(Base):
    """Daily referee assignments to games."""

    __tablename__ = "referee_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    game_id = Column(Integer, nullable=True)
    home_team = Column(String(3), nullable=False)
    away_team = Column(String(3), nullable=False)
    referee_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=True)  # referee, linesman

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ref_assignments_date", "date"),
    )

    def __repr__(self):
        return f"<RefereeAssignment {self.referee_name} - {self.home_team} vs {self.away_team}>"


class DataFetchLog(Base):
    """Track data fetching operations for freshness monitoring."""

    __tablename__ = "data_fetch_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    fetch_type = Column(String(50), nullable=False)  # schedule, stats, goalies, etc.
    status = Column(String(20), nullable=False)  # success, failed, partial
    records_fetched = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<DataFetchLog {self.source}/{self.fetch_type} ({self.status})>"
