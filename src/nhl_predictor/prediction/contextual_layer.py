"""Contextual Adjustment Layer (CAL).

Applies multipliers to base SPS based on game theory variables:
- Fatigue penalty (back-to-back)
- Travel penalty (timezone changes)
- Referee adjustment (home bias)
- Injury factor (key player out)
- Home ice advantage
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..config import get_config
from ..features.schedule_analyzer import ScheduleAnalyzer
from ..features.referee_analyzer import RefereeAnalyzer
from ..features.contextual_adjustments import ContextualAdjuster
from .sps_calculator import TeamSPS, MatchupSPS, SPSCalculator

logger = logging.getLogger(__name__)


@dataclass
class AdjustmentFactors:
    """Individual adjustment factors applied to a team."""

    # Base factors
    home_ice: float = 1.0  # Home ice advantage
    fatigue: float = 1.0  # Rest/schedule impact
    travel: float = 1.0  # Timezone/travel impact
    referee: float = 1.0  # Referee bias
    injury: float = 1.0  # Key player injuries
    desperation: float = 1.0  # Playoff race factor
    shooting_talent: float = 1.0  # Elite shooter boost

    # Combined multiplier
    total_multiplier: float = 1.0

    # Flags for explanation
    is_back_to_back: bool = False
    is_scheduled_loss: bool = False
    has_key_injury: bool = False
    is_desperate: bool = False


@dataclass
class AdjustedTeamSPS:
    """Team SPS after contextual adjustments."""

    team: str
    date: date

    # Original SPS
    raw_sps: float

    # Adjustments applied
    adjustments: AdjustmentFactors

    # Final adjusted SPS
    adjusted_sps: float

    # Component breakdown
    original_components: dict = field(default_factory=dict)


@dataclass
class AdjustedMatchup:
    """Full matchup analysis with adjustments."""

    home: AdjustedTeamSPS
    away: AdjustedTeamSPS

    # Differentials
    raw_differential: float  # Before adjustments
    adjusted_differential: float  # After adjustments

    # Key factors
    schedule_edge: str  # "home", "away", "neutral"
    goalie_edge: str
    key_factors: list  # List of significant factors


class ContextualAdjustmentLayer:
    """Applies contextual adjustments to SPS scores."""

    def __init__(self):
        """Initialize with default configuration."""
        config = get_config().model

        # Load adjustment scalars from config
        self.fatigue_penalty = config.fatigue_penalty  # 0.88
        self.travel_penalty = config.travel_penalty  # 0.94
        self.home_ice_advantage = config.home_ice_advantage  # 1.04
        self.referee_home_bias = config.referee_home_bias  # 1.03
        self.injury_penalty = config.injury_penalty  # 0.90

        # Initialize analyzers
        self.schedule_analyzer = ScheduleAnalyzer()
        self.referee_analyzer = RefereeAnalyzer()
        self.contextual_adjuster = ContextualAdjuster()
        self.sps_calculator = SPSCalculator()

    def calculate_adjustments(
        self,
        team: str,
        opponent: str,
        game_date: date,
        is_home: bool,
        injured_players: Optional[list[str]] = None,
    ) -> AdjustmentFactors:
        """
        Calculate all adjustment factors for a team.

        Args:
            team: Team code.
            opponent: Opponent team code.
            game_date: Date of the game.
            is_home: Whether team is playing at home.
            injured_players: List of injured player names.

        Returns:
            AdjustmentFactors with all multipliers.
        """
        factors = AdjustmentFactors()

        # 1. Home ice advantage
        if is_home:
            factors.home_ice = self.home_ice_advantage
        else:
            factors.home_ice = 1.0

        # 2. Fatigue/Schedule
        schedule = self.schedule_analyzer.get_team_schedule_context(team, game_date)

        if schedule.is_back_to_back:
            factors.fatigue = self.fatigue_penalty
            factors.is_back_to_back = True
        elif schedule.is_three_in_four:
            factors.fatigue = 0.92  # Less severe than B2B
        elif schedule.is_four_in_six:
            factors.fatigue = 0.94
        else:
            factors.fatigue = 1.0

        # 3. Travel penalty
        if schedule.timezone_change >= 3:
            factors.travel = self.travel_penalty
        elif schedule.timezone_change == 2:
            factors.travel = 0.97
        else:
            factors.travel = 1.0

        # 4. Referee adjustment (only for home team)
        if is_home:
            home_team = team
            away_team = opponent
        else:
            home_team = opponent
            away_team = team

        ref_analysis = self.referee_analyzer.get_game_referee_analysis(
            home_team, away_team, game_date
        )

        if is_home and ref_analysis.bias_tag == "home_friendly":
            factors.referee = self.referee_home_bias
        elif not is_home and ref_analysis.bias_tag == "away_friendly":
            factors.referee = 1.02  # Slight boost for away
        else:
            factors.referee = 1.0

        # 5. Injury factor
        injury_impact = self.contextual_adjuster.assess_injury_impact(
            team, injured_players
        )
        factors.injury = injury_impact.adjustment_factor
        factors.has_key_injury = injury_impact.has_key_injury

        # 6. Desperation factor
        desperation = self.contextual_adjuster.assess_desperation(team, game_date)
        factors.desperation = desperation.desperation_adjustment
        factors.is_desperate = desperation.is_desperate

        # 7. Shooting talent (in low-event matchups)
        low_event = self.contextual_adjuster.get_low_event_matchup_adjustment(
            home_team, away_team, game_date
        )
        if low_event["is_low_event"]:
            talent = self.contextual_adjuster.assess_shooting_talent(team, game_date)
            factors.shooting_talent = talent.talent_adjustment
        else:
            factors.shooting_talent = 1.0

        # Calculate total multiplier (all factors stacked)
        factors.total_multiplier = (
            factors.home_ice *
            factors.fatigue *
            factors.travel *
            factors.referee *
            factors.injury *
            factors.desperation *
            factors.shooting_talent
        )

        # Check for scheduled loss scenario
        if not is_home and factors.is_back_to_back:
            opp_schedule = self.schedule_analyzer.get_team_schedule_context(
                opponent, game_date
            )
            if opp_schedule.rest_days >= 2:
                factors.is_scheduled_loss = True

        return factors

    def apply_adjustments(
        self,
        team_sps: TeamSPS,
        opponent: str,
        is_home: bool,
        injured_players: Optional[list[str]] = None,
    ) -> AdjustedTeamSPS:
        """
        Apply contextual adjustments to a team's SPS.

        Args:
            team_sps: Original team SPS.
            opponent: Opponent team code.
            is_home: Whether team is playing at home.
            injured_players: List of injured players.

        Returns:
            AdjustedTeamSPS with adjustments applied.
        """
        adjustments = self.calculate_adjustments(
            team_sps.team,
            opponent,
            team_sps.date,
            is_home,
            injured_players,
        )

        adjusted_sps = team_sps.sps * adjustments.total_multiplier

        return AdjustedTeamSPS(
            team=team_sps.team,
            date=team_sps.date,
            raw_sps=team_sps.sps,
            adjustments=adjustments,
            adjusted_sps=adjusted_sps,
            original_components={
                "xgf_score": team_sps.xgf_score,
                "hdcf_score": team_sps.hdcf_score,
                "gsax_score": team_sps.gsax_score,
                "goalie": team_sps.goalie_name,
            },
        )

    def calculate_adjusted_matchup(
        self,
        home_team: str,
        away_team: str,
        game_date: date,
        home_goalie: Optional[str] = None,
        away_goalie: Optional[str] = None,
        home_injuries: Optional[list[str]] = None,
        away_injuries: Optional[list[str]] = None,
    ) -> Optional[AdjustedMatchup]:
        """
        Calculate fully adjusted matchup analysis.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.
            home_goalie: Home goalie name.
            away_goalie: Away goalie name.
            home_injuries: Home team injured players.
            away_injuries: Away team injured players.

        Returns:
            AdjustedMatchup with full analysis.
        """
        # Calculate raw SPS
        matchup_sps = self.sps_calculator.calculate_matchup_sps(
            home_team, away_team, game_date, home_goalie, away_goalie
        )

        if not matchup_sps:
            return None

        # Apply adjustments
        home_adjusted = self.apply_adjustments(
            matchup_sps.home_sps, away_team, True, home_injuries
        )
        away_adjusted = self.apply_adjustments(
            matchup_sps.away_sps, home_team, False, away_injuries
        )

        # Calculate differentials
        raw_diff = matchup_sps.sps_differential
        adjusted_diff = home_adjusted.adjusted_sps - away_adjusted.adjusted_sps

        # Determine edges
        schedule_analysis = self.schedule_analyzer.get_matchup_schedule_analysis(
            home_team, away_team, game_date
        )
        schedule_edge = schedule_analysis.schedule_edge

        goalie_edge = matchup_sps.advantage  # From raw SPS comparison

        # Identify key factors
        key_factors = self._identify_key_factors(
            home_adjusted, away_adjusted, schedule_analysis
        )

        return AdjustedMatchup(
            home=home_adjusted,
            away=away_adjusted,
            raw_differential=raw_diff,
            adjusted_differential=adjusted_diff,
            schedule_edge=schedule_edge,
            goalie_edge=goalie_edge,
            key_factors=key_factors,
        )

    def _identify_key_factors(
        self,
        home: AdjustedTeamSPS,
        away: AdjustedTeamSPS,
        schedule_analysis,
    ) -> list[str]:
        """Identify the most significant factors in the matchup."""
        factors = []

        # Schedule factors
        if away.adjustments.is_scheduled_loss:
            factors.append("SCHEDULED_LOSS: Away team B2B vs rested home")
        elif away.adjustments.is_back_to_back:
            factors.append("FATIGUE: Away team on back-to-back")
        elif home.adjustments.is_back_to_back:
            factors.append("FATIGUE: Home team on back-to-back")

        # Injury factors
        if home.adjustments.has_key_injury:
            factors.append("INJURY: Home team missing key player")
        if away.adjustments.has_key_injury:
            factors.append("INJURY: Away team missing key player")

        # Goalie factors
        home_gsax = home.original_components.get("gsax_score", 50)
        away_gsax = away.original_components.get("gsax_score", 50)
        if abs(home_gsax - away_gsax) > 20:
            better = "Home" if home_gsax > away_gsax else "Away"
            factors.append(f"GOALIE_MISMATCH: {better} team has better goalie")

        # Desperation
        if home.adjustments.is_desperate:
            factors.append("DESPERATION: Home team in playoff race")
        if away.adjustments.is_desperate:
            factors.append("DESPERATION: Away team in playoff race")

        # Travel
        if away.adjustments.travel < 0.95:
            factors.append("TRAVEL: Away team significant timezone change")

        return factors

    def get_adjustment_summary(self, adjusted: AdjustedTeamSPS) -> dict:
        """Get a human-readable summary of adjustments."""
        adj = adjusted.adjustments

        summary = {
            "team": adjusted.team,
            "raw_sps": round(adjusted.raw_sps, 1),
            "adjusted_sps": round(adjusted.adjusted_sps, 1),
            "total_adjustment": round((adj.total_multiplier - 1) * 100, 1),
            "factors": [],
        }

        if adj.home_ice != 1.0:
            summary["factors"].append(
                f"Home ice: +{(adj.home_ice - 1) * 100:.1f}%"
            )

        if adj.fatigue != 1.0:
            summary["factors"].append(
                f"Fatigue: {(adj.fatigue - 1) * 100:.1f}%"
            )

        if adj.travel != 1.0:
            summary["factors"].append(
                f"Travel: {(adj.travel - 1) * 100:.1f}%"
            )

        if adj.referee != 1.0:
            summary["factors"].append(
                f"Referee: +{(adj.referee - 1) * 100:.1f}%"
            )

        if adj.injury != 1.0:
            summary["factors"].append(
                f"Injury: {(adj.injury - 1) * 100:.1f}%"
            )

        return summary


def apply_contextual_adjustments(
    home_team: str,
    away_team: str,
    game_date: date,
) -> Optional[AdjustedMatchup]:
    """Convenience function to get adjusted matchup."""
    cal = ContextualAdjustmentLayer()
    return cal.calculate_adjusted_matchup(home_team, away_team, game_date)
