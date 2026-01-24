"""Model Calibration Module.

Tracks prediction accuracy and calibrates model performance over time.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import Prediction, Game

logger = logging.getLogger(__name__)


@dataclass
class CalibrationMetrics:
    """Calibration metrics for the model."""

    # Sample info
    period: str  # "7d", "30d", "season"
    predictions_count: int
    games_with_outcome: int

    # Accuracy metrics
    accuracy: float  # % of correct picks
    home_accuracy: float  # % correct when picking home
    away_accuracy: float  # % correct when picking away

    # Calibration metrics
    brier_score: float  # Lower is better (0 = perfect)
    log_loss: float  # Lower is better

    # Confidence breakdown
    high_confidence_accuracy: float  # Accuracy on >58% picks
    medium_confidence_accuracy: float  # Accuracy on 53-58% picks

    # Value metrics (if odds tracked)
    roi: Optional[float] = None  # Return on investment
    units_won: Optional[float] = None


@dataclass
class PredictionRecord:
    """Individual prediction record for tracking."""

    game_id: int
    date: date
    home_team: str
    away_team: str
    pick: str  # "home" or "away"
    pick_team: str
    model_prob: float
    market_prob: Optional[float]
    edge: Optional[float]
    actual_winner: Optional[str]
    correct: Optional[bool]
    kelly_score: Optional[float]


@dataclass
class CalibrationBucket:
    """Calibration bucket for probability ranges."""

    prob_range: str  # e.g., "50-55%"
    min_prob: float
    max_prob: float
    count: int
    wins: int
    actual_win_rate: float
    expected_win_rate: float
    calibration_error: float


class ModelCalibrator:
    """Tracks and calibrates model performance."""

    def __init__(self):
        """Initialize calibrator."""
        self.db = get_db()

    def record_prediction(
        self,
        game_id: int,
        home_team: str,
        away_team: str,
        home_prob: float,
        pick: str,
        market_prob: Optional[float] = None,
        edge: Optional[float] = None,
        kelly_score: Optional[float] = None,
    ) -> None:
        """
        Record a prediction in the database.

        Args:
            game_id: NHL game ID.
            home_team: Home team code.
            away_team: Away team code.
            home_prob: Model probability for home team.
            pick: "home" or "away".
            market_prob: Market implied probability for picked team.
            edge: Edge on the pick.
            kelly_score: Kelly criterion score.
        """
        with self.db.session_scope() as session:
            # Check if prediction exists
            existing = session.query(Prediction).filter(
                Prediction.game_id == game_id
            ).first()

            if existing:
                logger.debug(f"Prediction already exists for game {game_id}")
                return

            prediction = Prediction(
                game_id=game_id,
                home_win_prob=home_prob,
                away_win_prob=1 - home_prob,
                home_implied_prob=market_prob if pick == "home" else None,
                away_implied_prob=market_prob if pick == "away" else None,
                home_edge=edge if pick == "home" else -edge if edge else None,
                away_edge=edge if pick == "away" else -edge if edge else None,
                pick=home_team if pick == "home" else away_team,
                pick_confidence=home_prob if pick == "home" else 1 - home_prob,
                kelly_score=kelly_score,
            )
            session.add(prediction)

    def update_outcomes(self) -> int:
        """
        Update prediction outcomes from completed games.

        Returns:
            Number of predictions updated.
        """
        updated = 0

        with self.db.session_scope() as session:
            # Find predictions without outcomes
            pending = session.query(Prediction).filter(
                Prediction.actual_winner.is_(None)
            ).all()

            for pred in pending:
                # Get game result
                game = session.query(Game).filter(
                    Game.game_id == pred.game_id
                ).first()

                if game and game.winner:
                    pred.actual_winner = game.winner
                    pred.pick_correct = (pred.pick == game.winner)
                    updated += 1

        logger.info(f"Updated {updated} prediction outcomes")
        return updated

    def calculate_metrics(
        self,
        period: str = "30d",
        as_of_date: Optional[date] = None,
    ) -> CalibrationMetrics:
        """
        Calculate calibration metrics for a period.

        Args:
            period: Time period ("7d", "30d", "season").
            as_of_date: End date for period.

        Returns:
            CalibrationMetrics for the period.
        """
        if as_of_date is None:
            as_of_date = date.today()

        # Determine start date
        if period == "7d":
            start_date = as_of_date - timedelta(days=7)
        elif period == "30d":
            start_date = as_of_date - timedelta(days=30)
        else:  # season
            start_date = date(as_of_date.year if as_of_date.month >= 10 else as_of_date.year - 1, 10, 1)

        with self.db.session_scope() as session:
            # Get predictions with outcomes
            predictions = session.query(Prediction).join(
                Game, Prediction.game_id == Game.game_id
            ).filter(
                Game.date >= start_date,
                Game.date <= as_of_date,
                Prediction.actual_winner.isnot(None),
            ).all()

            if not predictions:
                return self._empty_metrics(period)

            # Calculate metrics
            total = len(predictions)
            correct = sum(1 for p in predictions if p.pick_correct)
            accuracy = correct / total if total > 0 else 0

            # Home/away split
            home_picks = [p for p in predictions if p.pick == p.game.home_team]
            away_picks = [p for p in predictions if p.pick != p.game.home_team]

            home_correct = sum(1 for p in home_picks if p.pick_correct)
            away_correct = sum(1 for p in away_picks if p.pick_correct)

            home_accuracy = home_correct / len(home_picks) if home_picks else 0
            away_accuracy = away_correct / len(away_picks) if away_picks else 0

            # Brier score and log loss
            brier = self._calculate_brier_score(predictions)
            log_loss = self._calculate_log_loss(predictions)

            # Confidence splits
            high_conf = [p for p in predictions if p.pick_confidence >= 0.58]
            med_conf = [p for p in predictions if 0.53 <= p.pick_confidence < 0.58]

            high_acc = (
                sum(1 for p in high_conf if p.pick_correct) / len(high_conf)
                if high_conf else 0
            )
            med_acc = (
                sum(1 for p in med_conf if p.pick_correct) / len(med_conf)
                if med_conf else 0
            )

            return CalibrationMetrics(
                period=period,
                predictions_count=total,
                games_with_outcome=total,
                accuracy=accuracy,
                home_accuracy=home_accuracy,
                away_accuracy=away_accuracy,
                brier_score=brier,
                log_loss=log_loss,
                high_confidence_accuracy=high_acc,
                medium_confidence_accuracy=med_acc,
            )

    def _calculate_brier_score(self, predictions: list) -> float:
        """
        Calculate Brier score for predictions.

        Brier = mean((predicted_prob - actual_outcome)^2)
        """
        if not predictions:
            return 0.0

        total = 0.0
        for p in predictions:
            prob = p.pick_confidence
            outcome = 1.0 if p.pick_correct else 0.0
            total += (prob - outcome) ** 2

        return total / len(predictions)

    def _calculate_log_loss(self, predictions: list) -> float:
        """
        Calculate log loss for predictions.

        LogLoss = -mean(outcome * log(prob) + (1-outcome) * log(1-prob))
        """
        if not predictions:
            return 0.0

        total = 0.0
        epsilon = 1e-15  # Avoid log(0)

        for p in predictions:
            prob = max(epsilon, min(1 - epsilon, p.pick_confidence))
            outcome = 1.0 if p.pick_correct else 0.0

            total += -(outcome * math.log(prob) + (1 - outcome) * math.log(1 - prob))

        return total / len(predictions)

    def _empty_metrics(self, period: str) -> CalibrationMetrics:
        """Return empty metrics when no data available."""
        return CalibrationMetrics(
            period=period,
            predictions_count=0,
            games_with_outcome=0,
            accuracy=0.0,
            home_accuracy=0.0,
            away_accuracy=0.0,
            brier_score=0.0,
            log_loss=0.0,
            high_confidence_accuracy=0.0,
            medium_confidence_accuracy=0.0,
        )

    def get_calibration_curve(
        self,
        bucket_size: float = 0.05,
        as_of_date: Optional[date] = None,
    ) -> list[CalibrationBucket]:
        """
        Get calibration curve data (predicted vs actual).

        Args:
            bucket_size: Size of probability buckets (default 5%).
            as_of_date: End date for analysis.

        Returns:
            List of CalibrationBucket objects.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            predictions = session.query(Prediction).filter(
                Prediction.actual_winner.isnot(None)
            ).all()

            if not predictions:
                return []

            # Create buckets
            buckets = []
            prob = 0.50

            while prob < 1.0:
                min_p = prob
                max_p = min(prob + bucket_size, 1.0)

                bucket_preds = [
                    p for p in predictions
                    if min_p <= p.pick_confidence < max_p
                ]

                if bucket_preds:
                    wins = sum(1 for p in bucket_preds if p.pick_correct)
                    count = len(bucket_preds)
                    actual_rate = wins / count
                    expected_rate = (min_p + max_p) / 2
                    error = abs(actual_rate - expected_rate)

                    buckets.append(CalibrationBucket(
                        prob_range=f"{min_p:.0%}-{max_p:.0%}",
                        min_prob=min_p,
                        max_prob=max_p,
                        count=count,
                        wins=wins,
                        actual_win_rate=actual_rate,
                        expected_win_rate=expected_rate,
                        calibration_error=error,
                    ))

                prob += bucket_size

            return buckets

    def identify_biases(
        self,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """
        Identify systematic biases in model predictions.

        Returns:
            Dict with identified biases and suggestions.
        """
        metrics = self.calculate_metrics("season", as_of_date)
        biases = []
        suggestions = []

        # Check home/away bias
        if abs(metrics.home_accuracy - metrics.away_accuracy) > 0.10:
            if metrics.home_accuracy > metrics.away_accuracy:
                biases.append("Model undervalues away teams")
                suggestions.append("Consider reducing home ice advantage weight")
            else:
                biases.append("Model overvalues away teams")
                suggestions.append("Consider increasing home ice advantage weight")

        # Check confidence calibration
        if metrics.high_confidence_accuracy < 0.55:
            biases.append("High confidence picks underperforming")
            suggestions.append("Model may be overconfident, consider dampening probabilities")

        if metrics.high_confidence_accuracy > 0.70:
            biases.append("High confidence picks outperforming predicted rate")
            suggestions.append("Model may be underconfident, consider boosting edge estimates")

        # Check Brier score
        if metrics.brier_score > 0.25:
            biases.append("Overall calibration is poor")
            suggestions.append("Review feature weights and contextual adjustments")

        return {
            "biases_detected": len(biases),
            "biases": biases,
            "suggestions": suggestions,
            "metrics": {
                "accuracy": f"{metrics.accuracy:.1%}",
                "home_accuracy": f"{metrics.home_accuracy:.1%}",
                "away_accuracy": f"{metrics.away_accuracy:.1%}",
                "brier_score": round(metrics.brier_score, 4),
                "high_conf_accuracy": f"{metrics.high_confidence_accuracy:.1%}",
            },
        }

    def get_performance_summary(self) -> dict:
        """Get overall performance summary."""
        metrics_7d = self.calculate_metrics("7d")
        metrics_30d = self.calculate_metrics("30d")
        metrics_season = self.calculate_metrics("season")

        return {
            "7_day": {
                "picks": metrics_7d.predictions_count,
                "accuracy": f"{metrics_7d.accuracy:.1%}",
                "brier": round(metrics_7d.brier_score, 4),
            },
            "30_day": {
                "picks": metrics_30d.predictions_count,
                "accuracy": f"{metrics_30d.accuracy:.1%}",
                "brier": round(metrics_30d.brier_score, 4),
            },
            "season": {
                "picks": metrics_season.predictions_count,
                "accuracy": f"{metrics_season.accuracy:.1%}",
                "brier": round(metrics_season.brier_score, 4),
            },
        }


def get_calibration_metrics(period: str = "30d") -> CalibrationMetrics:
    """Convenience function to get calibration metrics."""
    calibrator = ModelCalibrator()
    return calibrator.calculate_metrics(period)


def record_prediction(
    game_id: int,
    home_team: str,
    away_team: str,
    home_prob: float,
    pick: str,
) -> None:
    """Convenience function to record a prediction."""
    calibrator = ModelCalibrator()
    calibrator.record_prediction(game_id, home_team, away_team, home_prob, pick)
