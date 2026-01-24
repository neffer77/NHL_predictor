"""Contextual adjustments for predictions.

Handles injury impact, shooting talent, coach systems, and desperation factors.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models.database import get_db
from ..models.schema import TeamDailyStats, Game

logger = logging.getLogger(__name__)


@dataclass
class InjuryImpact:
    """Injury impact assessment for a team."""

    team: str
    has_key_injury: bool
    mvp_out: bool
    injured_players: list[str]
    scoring_impact: float  # % of scoring affected
    adjustment_factor: float  # 0.90 - 1.0


@dataclass
class ShootingTalentMetrics:
    """Shooting talent assessment for a team."""

    team: str
    shooting_talent_score: float  # Above/below average
    has_elite_shooters: bool
    elite_shooter_names: list[str]
    talent_adjustment: float  # 0.98 - 1.05


@dataclass
class CoachSystemProfile:
    """Coach system classification."""

    team: str
    system_type: str  # "low_event", "high_event", "neutral"
    avg_xg_per_60: float
    avg_xga_per_60: float
    combined_xg_per_60: float
    is_defensive_system: bool
    is_aggressive_system: bool


@dataclass
class DesperationFactor:
    """Playoff race desperation assessment."""

    team: str
    games_played: int
    points: int
    playoff_cutoff_points: int
    points_from_cutoff: int
    is_desperate: bool  # Fighting for playoff spot
    is_eliminated: bool  # Mathematically out
    is_clinched: bool  # Playoff spot secured
    desperation_adjustment: float  # 0.95 - 1.05


class ContextualAdjuster:
    """Calculates contextual adjustments for predictions."""

    # Elite shooters list (would be updated throughout season)
    ELITE_SHOOTERS = {
        "TOR": ["Auston Matthews", "Mitch Marner"],
        "EDM": ["Connor McDavid", "Leon Draisaitl"],
        "COL": ["Nathan MacKinnon", "Mikko Rantanen"],
        "FLA": ["Aleksander Barkov", "Sam Reinhart"],
        "TBL": ["Nikita Kucherov", "Brayden Point"],
        "DAL": ["Jason Robertson", "Roope Hintz"],
        "VGK": ["Jack Eichel", "Mark Stone"],
        "NYR": ["Artemi Panarin", "Mika Zibanejad"],
        "NJD": ["Jack Hughes", "Jesper Bratt"],
        "CAR": ["Sebastian Aho", "Andrei Svechnikov"],
        "BOS": ["David Pastrnak", "Brad Marchand"],
        "WPG": ["Kyle Connor", "Mark Scheifele"],
        "VAN": ["Elias Pettersson", "J.T. Miller"],
        "CHI": ["Connor Bedard"],
    }

    # Injury adjustment factor
    MVP_OUT_ADJUSTMENT = 0.90
    KEY_PLAYER_OUT_ADJUSTMENT = 0.95

    # Playoff cutoff (approximate for 82-game season)
    PLAYOFF_CUTOFF_PACE = 95  # Points needed for playoff spot

    def __init__(self):
        self.db = get_db()

    def assess_injury_impact(
        self,
        team: str,
        injured_players: Optional[list[str]] = None,
    ) -> InjuryImpact:
        """
        Assess the impact of injuries on a team.

        Args:
            team: Team code.
            injured_players: List of injured player names.

        Returns:
            InjuryImpact assessment.
        """
        if injured_players is None:
            injured_players = []

        # Check if any elite shooters are injured
        elite_shooters = self.ELITE_SHOOTERS.get(team, [])
        mvp_out = False
        key_injuries = []

        for player in injured_players:
            if player in elite_shooters:
                key_injuries.append(player)
                if elite_shooters.index(player) == 0:  # Top player
                    mvp_out = True

        # Calculate adjustment
        if mvp_out:
            adjustment = self.MVP_OUT_ADJUSTMENT
        elif key_injuries:
            adjustment = self.KEY_PLAYER_OUT_ADJUSTMENT
        else:
            adjustment = 1.0

        # Estimate scoring impact
        scoring_impact = 0.0
        if mvp_out:
            scoring_impact = 0.30  # Top scorer often 25-35% of team
        elif key_injuries:
            scoring_impact = len(key_injuries) * 0.10

        return InjuryImpact(
            team=team,
            has_key_injury=bool(key_injuries),
            mvp_out=mvp_out,
            injured_players=injured_players,
            scoring_impact=scoring_impact,
            adjustment_factor=adjustment,
        )

    def assess_shooting_talent(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> ShootingTalentMetrics:
        """
        Assess a team's shooting talent.

        Higher shooting talent means xG models undervalue the team.

        Args:
            team: Team code.
            as_of_date: Date for assessment.

        Returns:
            ShootingTalentMetrics.
        """
        elite_shooters = self.ELITE_SHOOTERS.get(team, [])
        has_elite = len(elite_shooters) > 0

        # Base talent score on number of elite shooters
        if len(elite_shooters) >= 2:
            talent_score = 1.05
        elif len(elite_shooters) == 1:
            talent_score = 1.02
        else:
            talent_score = 1.0

        # In a full implementation, this would use MoneyPuck's
        # shooting talent data

        return ShootingTalentMetrics(
            team=team,
            shooting_talent_score=talent_score,
            has_elite_shooters=has_elite,
            elite_shooter_names=elite_shooters,
            talent_adjustment=talent_score,
        )

    def classify_coach_system(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> CoachSystemProfile:
        """
        Classify a team's coaching system.

        Low-event systems suppress both xGF and xGA.
        High-event systems generate and allow many chances.

        Args:
            team: Team code.
            as_of_date: Date for assessment.

        Returns:
            CoachSystemProfile.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
            ).order_by(TeamDailyStats.date.desc()).first()

            if not stats:
                return CoachSystemProfile(
                    team=team,
                    system_type="neutral",
                    avg_xg_per_60=2.5,
                    avg_xga_per_60=2.5,
                    combined_xg_per_60=5.0,
                    is_defensive_system=False,
                    is_aggressive_system=False,
                )

            games = stats.games_played or 1
            xgf = stats.xgf or 0
            xga = stats.xga or 0

            # Calculate per-60 rates (approximate)
            xg_per_60 = (xgf / games) * 3  # ~20 min periods
            xga_per_60 = (xga / games) * 3
            combined = xg_per_60 + xga_per_60

            # Classify system
            if combined < 4.5:
                system_type = "low_event"
                is_defensive = True
                is_aggressive = False
            elif combined > 5.5:
                system_type = "high_event"
                is_defensive = False
                is_aggressive = True
            else:
                system_type = "neutral"
                is_defensive = False
                is_aggressive = False

            return CoachSystemProfile(
                team=team,
                system_type=system_type,
                avg_xg_per_60=xg_per_60,
                avg_xga_per_60=xga_per_60,
                combined_xg_per_60=combined,
                is_defensive_system=is_defensive,
                is_aggressive_system=is_aggressive,
            )

    def assess_desperation(
        self,
        team: str,
        as_of_date: Optional[date] = None,
    ) -> DesperationFactor:
        """
        Assess playoff race desperation.

        Desperate teams may play harder but take more risks.

        Args:
            team: Team code.
            as_of_date: Date for assessment.

        Returns:
            DesperationFactor.
        """
        if as_of_date is None:
            as_of_date = date.today()

        with self.db.session_scope() as session:
            stats = session.query(TeamDailyStats).filter(
                TeamDailyStats.team == team,
                TeamDailyStats.date <= as_of_date,
                TeamDailyStats.source == "nhl_api",
            ).order_by(TeamDailyStats.date.desc()).first()

            if not stats:
                return DesperationFactor(
                    team=team,
                    games_played=0,
                    points=0,
                    playoff_cutoff_points=self.PLAYOFF_CUTOFF_PACE,
                    points_from_cutoff=0,
                    is_desperate=False,
                    is_eliminated=False,
                    is_clinched=False,
                    desperation_adjustment=1.0,
                )

            games = stats.games_played or 0
            points = stats.points or 0

            # Calculate points pace
            if games > 0:
                points_pace = (points / games) * 82
            else:
                points_pace = 0

            # Estimate playoff cutoff at current point in season
            cutoff_pace = self.PLAYOFF_CUTOFF_PACE * (games / 82)
            points_from_cutoff = points - cutoff_pace

            # Only apply desperation after March 1st (game 60+)
            is_late_season = games >= 60

            # Determine status
            if points_pace >= 105:  # Lock for playoffs
                is_clinched = True
                is_desperate = False
                is_eliminated = False
            elif points_pace <= 75 and is_late_season:  # Out of race
                is_clinched = False
                is_desperate = False
                is_eliminated = True
            elif -5 <= points_from_cutoff <= 5 and is_late_season:
                is_clinched = False
                is_desperate = True
                is_eliminated = False
            else:
                is_clinched = False
                is_desperate = False
                is_eliminated = False

            # Calculate adjustment
            if is_desperate:
                adjustment = 1.02  # Slight boost for effort
            elif is_eliminated:
                adjustment = 0.98  # Slight decrease for lack of motivation
            else:
                adjustment = 1.0

            return DesperationFactor(
                team=team,
                games_played=games,
                points=points,
                playoff_cutoff_points=int(cutoff_pace),
                points_from_cutoff=int(points_from_cutoff),
                is_desperate=is_desperate,
                is_eliminated=is_eliminated,
                is_clinched=is_clinched,
                desperation_adjustment=adjustment,
            )

    def get_low_event_matchup_adjustment(
        self,
        home_team: str,
        away_team: str,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """
        Get adjustment for low-event matchups.

        In low-event games, individual talent matters more.

        Returns:
            Dict with matchup type and talent adjustments.
        """
        home_system = self.classify_coach_system(home_team, as_of_date)
        away_system = self.classify_coach_system(away_team, as_of_date)

        combined_xg = (
            home_system.combined_xg_per_60 + away_system.combined_xg_per_60
        ) / 2

        is_low_event = combined_xg < 4.5

        # In low-event games, boost shooting talent importance
        if is_low_event:
            home_talent = self.assess_shooting_talent(home_team, as_of_date)
            away_talent = self.assess_shooting_talent(away_team, as_of_date)

            return {
                "is_low_event": True,
                "expected_combined_xg": combined_xg,
                "home_talent_boost": home_talent.talent_adjustment * 1.02,
                "away_talent_boost": away_talent.talent_adjustment * 1.02,
            }

        return {
            "is_low_event": False,
            "expected_combined_xg": combined_xg,
            "home_talent_boost": 1.0,
            "away_talent_boost": 1.0,
        }


def assess_injury_impact(
    team: str,
    injured_players: Optional[list[str]] = None,
) -> InjuryImpact:
    """Convenience function to assess injury impact."""
    adjuster = ContextualAdjuster()
    return adjuster.assess_injury_impact(team, injured_players)


def assess_desperation(team: str) -> DesperationFactor:
    """Convenience function to assess desperation factor."""
    adjuster = ContextualAdjuster()
    return adjuster.assess_desperation(team)


def classify_system(team: str) -> CoachSystemProfile:
    """Convenience function to classify coach system."""
    adjuster = ContextualAdjuster()
    return adjuster.classify_coach_system(team)
