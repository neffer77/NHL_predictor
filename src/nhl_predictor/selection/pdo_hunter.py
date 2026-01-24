"""PDO Mismatch Hunter.

Identifies high-value matchups where PDO regression is likely to
create value opportunities. Looks for games where:
- One team has unsustainably high PDO (due for regression down)
- One team has unsustainably low PDO (due for regression up)
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats, Game
from ..features.pdo_tracker import PDOTracker

logger = logging.getLogger(__name__)


@dataclass
class PDOMismatch:
    """PDO mismatch between two teams."""

    # Game info
    game_id: int
    home_team: str
    away_team: str
    game_date: date

    # PDO values
    home_pdo: float
    away_pdo: float
    pdo_differential: float

    # Components
    home_sh_pct: float  # Shooting %
    home_sv_pct: float  # Save %
    away_sh_pct: float
    away_sv_pct: float

    # Regression expectations
    home_expected_regression: float  # Positive = expected to increase
    away_expected_regression: float

    # Value assessment
    value_side: str  # "home", "away", or "none"
    value_edge: float
    mismatch_severity: str  # "extreme", "significant", "moderate", "none"

    # Explanation
    explanation: str


@dataclass
class PDOHuntResult:
    """Results of PDO hunting for a day."""

    date: date
    games_analyzed: int
    mismatches_found: int
    mismatches: list[PDOMismatch]
    best_opportunity: Optional[PDOMismatch]


class PDOMismatchHunter:
    """Hunts for PDO-based value opportunities."""

    # PDO thresholds
    LEAGUE_AVERAGE_PDO = 1000
    EXTREME_HIGH = 1025  # Very unsustainably high
    HIGH = 1015  # Unsustainably high
    LOW = 985  # Unsustainably low
    EXTREME_LOW = 975  # Very unsustainably low

    # Shooting/save percentage thresholds
    UNSUSTAINABLE_SH_PCT = 11.0  # League avg ~9%
    UNSUSTAINABLE_SV_PCT = 0.925  # League avg ~.910

    # Minimum games for reliable PDO
    MIN_GAMES = 15

    def __init__(self):
        """Initialize PDO hunter."""
        self.db = get_db()
        self.pdo_tracker = PDOTracker()

    def hunt_daily_mismatches(
        self,
        game_date: Optional[date] = None,
    ) -> PDOHuntResult:
        """
        Hunt for PDO mismatches in all games for a date.

        Args:
            game_date: Date to analyze.

        Returns:
            PDOHuntResult with all findings.
        """
        if game_date is None:
            game_date = date.today()

        mismatches = []

        with self.db.session_scope() as session:
            games = session.query(Game).filter(
                Game.date == game_date
            ).all()

            for game in games:
                mismatch = self.analyze_matchup(
                    game.home_team,
                    game.away_team,
                    game_date,
                    game.game_id,
                )

                if mismatch and mismatch.mismatch_severity != "none":
                    mismatches.append(mismatch)

        # Sort by value edge
        mismatches.sort(key=lambda m: m.value_edge, reverse=True)

        return PDOHuntResult(
            date=game_date,
            games_analyzed=len(games) if games else 0,
            mismatches_found=len(mismatches),
            mismatches=mismatches,
            best_opportunity=mismatches[0] if mismatches else None,
        )

    def analyze_matchup(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
        game_id: Optional[int] = None,
    ) -> Optional[PDOMismatch]:
        """
        Analyze PDO mismatch for a specific matchup.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Game date.
            game_id: NHL game ID.

        Returns:
            PDOMismatch if mismatch found, None otherwise.
        """
        home_pdo = self._get_team_pdo(home_team, game_date)
        away_pdo = self._get_team_pdo(away_team, game_date)

        if not home_pdo or not away_pdo:
            return None

        # Calculate differential
        differential = home_pdo["pdo"] - away_pdo["pdo"]

        # Calculate expected regression for each team
        home_regression = self._calculate_regression(home_pdo["pdo"])
        away_regression = self._calculate_regression(away_pdo["pdo"])

        # Determine value side and severity
        value_side, value_edge, severity = self._assess_mismatch(
            home_pdo, away_pdo, home_regression, away_regression
        )

        # Generate explanation
        explanation = self._generate_explanation(
            home_team, away_team, home_pdo, away_pdo,
            home_regression, away_regression, value_side
        )

        return PDOMismatch(
            game_id=game_id or 0,
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            home_pdo=home_pdo["pdo"],
            away_pdo=away_pdo["pdo"],
            pdo_differential=differential,
            home_sh_pct=home_pdo["sh_pct"],
            home_sv_pct=home_pdo["sv_pct"],
            away_sh_pct=away_pdo["sh_pct"],
            away_sv_pct=away_pdo["sv_pct"],
            home_expected_regression=home_regression,
            away_expected_regression=away_regression,
            value_side=value_side,
            value_edge=value_edge,
            mismatch_severity=severity,
            explanation=explanation,
        )

    def _get_team_pdo(
        self,
        team: str,
        as_of_date: date,
    ) -> Optional[dict]:
        """Get team's current PDO data."""
        with self.db.session_scope() as session:
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
            ).order_by(TeamDailyStats.date.desc()).first()

            if not stats or not stats.games_played:
                return None

            if stats.games_played < self.MIN_GAMES:
                # Not enough data for reliable PDO
                return None

            return {
                "pdo": stats.pdo or 1000,
                "sh_pct": stats.sh_pct or 9.0,
                "sv_pct": stats.sv_pct or 0.910,
                "games": stats.games_played,
            }

    def _calculate_regression(self, pdo: float) -> float:
        """
        Calculate expected regression toward 1000.

        Positive = expected to go up, Negative = expected to go down.
        """
        # Simple linear regression to mean
        # PDO of 1020 should regress ~6-8 points on average
        regression_rate = 0.3  # 30% regression expected over next ~10 games

        return (self.LEAGUE_AVERAGE_PDO - pdo) * regression_rate

    def _assess_mismatch(
        self,
        home_pdo: dict,
        away_pdo: dict,
        home_regression: float,
        away_regression: float,
    ) -> tuple[str, float, str]:
        """
        Assess the mismatch between two teams' PDO.

        Returns:
            Tuple of (value_side, value_edge, severity).
        """
        home_p = home_pdo["pdo"]
        away_p = away_pdo["pdo"]

        # Calculate value edge based on regression expectations
        # If home team is due to regress down and away due to regress up,
        # there's value on away team
        regression_diff = away_regression - home_regression

        # Positive regression_diff means away team should improve relative to home
        if regression_diff > 3:
            value_side = "away"
            value_edge = regression_diff / 100  # Convert to percentage
        elif regression_diff < -3:
            value_side = "home"
            value_edge = abs(regression_diff) / 100
        else:
            value_side = "none"
            value_edge = 0.0

        # Determine severity
        pdo_diff = abs(home_p - away_p)

        if pdo_diff >= 40:
            severity = "extreme"
        elif pdo_diff >= 25:
            severity = "significant"
        elif pdo_diff >= 15:
            severity = "moderate"
        else:
            severity = "none"

        return value_side, value_edge, severity

    def _generate_explanation(
        self,
        home_team: str,
        away_team: str,
        home_pdo: dict,
        away_pdo: dict,
        home_regression: float,
        away_regression: float,
        value_side: str,
    ) -> str:
        """Generate human-readable explanation."""
        explanations = []

        home_p = home_pdo["pdo"]
        away_p = away_pdo["pdo"]

        # Home team assessment
        if home_p >= self.EXTREME_HIGH:
            explanations.append(
                f"{home_team} has extremely high PDO ({home_p:.0f}), "
                f"major regression expected ({home_regression:+.0f})"
            )
        elif home_p >= self.HIGH:
            explanations.append(
                f"{home_team} has unsustainably high PDO ({home_p:.0f}), "
                f"regression likely ({home_regression:+.0f})"
            )
        elif home_p <= self.EXTREME_LOW:
            explanations.append(
                f"{home_team} has extremely low PDO ({home_p:.0f}), "
                f"due for positive regression ({home_regression:+.0f})"
            )
        elif home_p <= self.LOW:
            explanations.append(
                f"{home_team} has low PDO ({home_p:.0f}), "
                f"positive regression expected ({home_regression:+.0f})"
            )

        # Away team assessment
        if away_p >= self.EXTREME_HIGH:
            explanations.append(
                f"{away_team} has extremely high PDO ({away_p:.0f}), "
                f"major regression expected ({away_regression:+.0f})"
            )
        elif away_p >= self.HIGH:
            explanations.append(
                f"{away_team} has unsustainably high PDO ({away_p:.0f}), "
                f"regression likely ({away_regression:+.0f})"
            )
        elif away_p <= self.EXTREME_LOW:
            explanations.append(
                f"{away_team} has extremely low PDO ({away_p:.0f}), "
                f"due for positive regression ({away_regression:+.0f})"
            )
        elif away_p <= self.LOW:
            explanations.append(
                f"{away_team} has low PDO ({away_p:.0f}), "
                f"positive regression expected ({away_regression:+.0f})"
            )

        # Value conclusion
        if value_side == "home":
            explanations.append(f"Value side: {home_team} (home)")
        elif value_side == "away":
            explanations.append(f"Value side: {away_team} (away)")
        else:
            explanations.append("No clear value side from PDO analysis")

        return " | ".join(explanations) if explanations else "PDO within normal range"

    def find_extreme_mismatches(
        self,
        game_date: Optional[date] = None,
        min_pdo_diff: float = 25,
    ) -> list[PDOMismatch]:
        """
        Find only extreme PDO mismatches.

        Args:
            game_date: Date to analyze.
            min_pdo_diff: Minimum PDO differential to consider.

        Returns:
            List of extreme PDOMismatch objects.
        """
        result = self.hunt_daily_mismatches(game_date)

        return [
            m for m in result.mismatches
            if abs(m.pdo_differential) >= min_pdo_diff
        ]

    def get_regression_candidates(
        self,
        game_date: Optional[date] = None,
    ) -> dict:
        """
        Get teams most likely to regress in either direction.

        Returns:
            Dict with 'regress_down' and 'regress_up' team lists.
        """
        if game_date is None:
            game_date = date.today()

        regress_down = []
        regress_up = []

        with self.db.session_scope() as session:
            # Get all teams' PDO
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.date <= game_date,
            ).order_by(
                TeamDailyStats.team,
                TeamDailyStats.date.desc()
            ).distinct(TeamDailyStats.team).all()

            for stat in stats:
                if not stat.pdo or stat.games_played < self.MIN_GAMES:
                    continue

                regression = self._calculate_regression(stat.pdo)

                if stat.pdo >= self.HIGH:
                    regress_down.append({
                        "team": stat.team,
                        "pdo": stat.pdo,
                        "expected_regression": regression,
                        "severity": "extreme" if stat.pdo >= self.EXTREME_HIGH else "high",
                    })
                elif stat.pdo <= self.LOW:
                    regress_up.append({
                        "team": stat.team,
                        "pdo": stat.pdo,
                        "expected_regression": regression,
                        "severity": "extreme" if stat.pdo <= self.EXTREME_LOW else "low",
                    })

        # Sort by PDO deviation
        regress_down.sort(key=lambda x: x["pdo"], reverse=True)
        regress_up.sort(key=lambda x: x["pdo"])

        return {
            "regress_down": regress_down,
            "regress_up": regress_up,
        }

    def analyze_shooting_luck(
        self,
        team: str,
        game_date: Optional[date] = None,
    ) -> dict:
        """
        Analyze shooting/save luck components of PDO.

        Returns:
            Dict with luck analysis.
        """
        if game_date is None:
            game_date = date.today()

        pdo_data = self._get_team_pdo(team, game_date)

        if not pdo_data:
            return {"error": "Insufficient data"}

        # League averages
        league_sh = 9.0
        league_sv = 0.910

        sh_luck = pdo_data["sh_pct"] - league_sh
        sv_luck = (pdo_data["sv_pct"] - league_sv) * 100  # Convert to points

        return {
            "team": team,
            "pdo": pdo_data["pdo"],
            "shooting_pct": pdo_data["sh_pct"],
            "save_pct": pdo_data["sv_pct"],
            "shooting_luck": sh_luck,
            "save_luck": sv_luck,
            "shooting_luck_label": (
                "hot" if sh_luck > 1.5 else
                "cold" if sh_luck < -1.5 else
                "normal"
            ),
            "save_luck_label": (
                "hot" if sv_luck > 1.5 else
                "cold" if sv_luck < -1.5 else
                "normal"
            ),
            "total_luck_points": round(pdo_data["pdo"] - 1000, 0),
        }


def hunt_pdo_mismatches(
    game_date: Optional[date] = None,
) -> PDOHuntResult:
    """Convenience function to hunt PDO mismatches."""
    hunter = PDOMismatchHunter()
    return hunter.hunt_daily_mismatches(game_date)


def get_best_pdo_play(
    game_date: Optional[date] = None,
) -> Optional[PDOMismatch]:
    """Convenience function to get best PDO play."""
    result = hunt_pdo_mismatches(game_date)
    return result.best_opportunity
