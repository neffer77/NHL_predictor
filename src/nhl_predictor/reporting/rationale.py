"""Rationale Generator.

Auto-generates human-readable explanations for each pick based on
the factors that contributed most to the selection.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..selection.selector import FinalPick
from ..selection.stability import StabilityChecker
from ..features.schedule_analyzer import ScheduleAnalyzer
from ..features.gsax_calculator import GSAxCalculator
from ..features.pdo_tracker import PDOTracker

logger = logging.getLogger(__name__)


@dataclass
class RationaleFactors:
    """Factors contributing to pick rationale."""

    # Primary factor
    primary_factor: str
    primary_description: str

    # Secondary factors
    secondary_factors: list[str]

    # Full rationale
    short_rationale: str  # 1-2 sentences
    detailed_rationale: str  # Full breakdown


class RationaleGenerator:
    """Generates human-readable rationales for picks."""

    # Factor thresholds
    GOALIE_MISMATCH_THRESHOLD = 5.0  # GSAx differential
    SCHEDULE_ADVANTAGE_THRESHOLD = 2  # Rest days advantage
    PDO_MISMATCH_THRESHOLD = 25  # PDO differential
    HIGH_EDGE_THRESHOLD = 0.05  # 5% edge

    def __init__(self):
        """Initialize rationale generator."""
        self.schedule_analyzer = ScheduleAnalyzer()
        self.gsax_calculator = GSAxCalculator()
        self.pdo_tracker = PDOTracker()
        self.stability_checker = StabilityChecker()

    def generate_rationale(
        self,
        pick: FinalPick,
        as_of_date: Optional[date] = None,
    ) -> RationaleFactors:
        """
        Generate rationale for a pick.

        Args:
            pick: FinalPick object.
            as_of_date: Date for context.

        Returns:
            RationaleFactors with explanation.
        """
        if as_of_date is None:
            as_of_date = pick.game_date

        # Collect all factors
        factors = self._analyze_factors(pick, as_of_date)

        # Prioritize factors by impact
        prioritized = self._prioritize_factors(factors)

        # Generate text
        primary = prioritized[0] if prioritized else ("edge", "Positive edge over market")
        secondary = prioritized[1:3] if len(prioritized) > 1 else []

        short_rationale = self._generate_short_rationale(pick, primary, secondary)
        detailed_rationale = self._generate_detailed_rationale(pick, prioritized)

        return RationaleFactors(
            primary_factor=primary[0],
            primary_description=primary[1],
            secondary_factors=[f[1] for f in secondary],
            short_rationale=short_rationale,
            detailed_rationale=detailed_rationale,
        )

    def _analyze_factors(
        self,
        pick: FinalPick,
        as_of_date: date,
    ) -> list[tuple[str, str, float]]:
        """
        Analyze all factors contributing to the pick.

        Returns:
            List of (factor_type, description, impact_score) tuples.
        """
        factors = []

        # 1. Edge analysis
        if pick.edge >= self.HIGH_EDGE_THRESHOLD:
            factors.append((
                "high_edge",
                f"Strong {pick.edge:.1%} edge over market",
                pick.edge * 10,
            ))
        elif pick.edge >= 0.03:
            factors.append((
                "good_edge",
                f"Solid {pick.edge:.1%} edge versus implied odds",
                pick.edge * 8,
            ))

        # 2. Model confidence
        if pick.model_probability >= 0.62:
            factors.append((
                "high_confidence",
                f"High model confidence at {pick.model_probability:.1%}",
                (pick.model_probability - 0.5) * 5,
            ))
        elif pick.model_probability >= 0.58:
            factors.append((
                "solid_confidence",
                f"Strong model confidence at {pick.model_probability:.1%}",
                (pick.model_probability - 0.5) * 4,
            ))

        # 3. Goalie mismatch
        goalie_factor = self._analyze_goalie_factor(pick, as_of_date)
        if goalie_factor:
            factors.append(goalie_factor)

        # 4. Schedule spot
        schedule_factor = self._analyze_schedule_factor(pick, as_of_date)
        if schedule_factor:
            factors.append(schedule_factor)

        # 5. PDO regression
        pdo_factor = self._analyze_pdo_factor(pick, as_of_date)
        if pdo_factor:
            factors.append(pdo_factor)

        # 6. Stability advantage
        if pick.stability_score >= 70:
            factors.append((
                "stable_team",
                f"Picking stable, consistent team (score: {pick.stability_score:.0f})",
                0.3,
            ))

        # 7. Low regression risk
        if pick.regression_risk == "low":
            factors.append((
                "sustainable",
                "No PDO regression concerns",
                0.2,
            ))

        # 8. Confirmed goalie advantage
        if pick.goalie_confirmed:
            factors.append((
                "goalie_confirmed",
                f"Confirmed starter: {pick.goalie_name}",
                0.25,
            ))

        # 9. Risk assessment
        if pick.risk_level == "low":
            factors.append((
                "low_risk",
                "Low overall risk profile",
                0.2,
            ))

        return factors

    def _analyze_goalie_factor(
        self,
        pick: FinalPick,
        as_of_date: date,
    ) -> Optional[tuple[str, str, float]]:
        """Analyze goalie mismatch factor."""
        try:
            # Get GSAx for both teams' goalies
            pick_gsax = self.gsax_calculator.get_goalie_gsax(
                pick.pick_team, as_of_date
            )
            opp_gsax = self.gsax_calculator.get_goalie_gsax(
                pick.opponent, as_of_date
            )

            if pick_gsax and opp_gsax:
                differential = pick_gsax.rolling_10_gsax - opp_gsax.rolling_10_gsax

                if differential >= self.GOALIE_MISMATCH_THRESHOLD:
                    return (
                        "goalie_mismatch",
                        f"Goalie advantage ({pick.goalie_name} +{differential:.1f} GSAx differential)",
                        differential * 0.15,
                    )
                elif differential >= 3.0:
                    return (
                        "goalie_edge",
                        f"Goalie edge in net ({pick.goalie_name} +{differential:.1f} GSAx)",
                        differential * 0.12,
                    )
        except Exception as e:
            logger.debug(f"Could not analyze goalie factor: {e}")

        return None

    def _analyze_schedule_factor(
        self,
        pick: FinalPick,
        as_of_date: date,
    ) -> Optional[tuple[str, str, float]]:
        """Analyze schedule spot factor."""
        try:
            matchup = self.schedule_analyzer.get_matchup_schedule_analysis(
                pick.home_team, pick.away_team, as_of_date
            )

            # Check if picked team has schedule advantage
            if pick.pick_side == "home":
                pick_rest = matchup.home_rest_days
                opp_rest = matchup.away_rest_days
                pick_b2b = matchup.home_back_to_back
                opp_b2b = matchup.away_back_to_back
            else:
                pick_rest = matchup.away_rest_days
                opp_rest = matchup.home_rest_days
                pick_b2b = matchup.away_back_to_back
                opp_b2b = matchup.home_back_to_back

            rest_advantage = pick_rest - opp_rest

            if opp_b2b and not pick_b2b:
                return (
                    "schedule_b2b",
                    f"Opponent on back-to-back ({pick.opponent} fatigued)",
                    0.6,
                )
            elif rest_advantage >= self.SCHEDULE_ADVANTAGE_THRESHOLD:
                return (
                    "rest_advantage",
                    f"Rest advantage ({rest_advantage} more days rest)",
                    rest_advantage * 0.15,
                )
            elif matchup.is_scheduled_loss and pick.pick_side == "home":
                return (
                    "scheduled_loss_fade",
                    f"Fading {pick.opponent} in scheduled loss spot",
                    0.5,
                )
        except Exception as e:
            logger.debug(f"Could not analyze schedule factor: {e}")

        return None

    def _analyze_pdo_factor(
        self,
        pick: FinalPick,
        as_of_date: date,
    ) -> Optional[tuple[str, str, float]]:
        """Analyze PDO regression factor."""
        try:
            pick_pdo = self.pdo_tracker.get_team_pdo(pick.pick_team, as_of_date)
            opp_pdo = self.pdo_tracker.get_team_pdo(pick.opponent, as_of_date)

            if pick_pdo and opp_pdo:
                pick_val = pick_pdo.rolling_10_pdo
                opp_val = opp_pdo.rolling_10_pdo
                differential = opp_val - pick_val

                if differential >= self.PDO_MISMATCH_THRESHOLD:
                    return (
                        "pdo_mismatch",
                        f"PDO regression play ({pick.opponent} at {opp_val:.0f}, due for drop)",
                        differential * 0.02,
                    )
                elif pick_val <= 985 and opp_val >= 1015:
                    return (
                        "pdo_bounce",
                        f"PDO bounce-back candidate ({pick.pick_team} due for positive regression)",
                        0.4,
                    )
        except Exception as e:
            logger.debug(f"Could not analyze PDO factor: {e}")

        return None

    def _prioritize_factors(
        self,
        factors: list[tuple[str, str, float]],
    ) -> list[tuple[str, str]]:
        """Prioritize factors by impact score."""
        # Sort by impact score descending
        sorted_factors = sorted(factors, key=lambda x: x[2], reverse=True)

        # Return just the type and description
        return [(f[0], f[1]) for f in sorted_factors]

    def _generate_short_rationale(
        self,
        pick: FinalPick,
        primary: tuple[str, str],
        secondary: list[tuple[str, str]],
    ) -> str:
        """Generate 1-2 sentence rationale."""
        sentences = []

        # Primary factor
        factor_type, description = primary
        sentences.append(description)

        # Add one secondary if impactful
        if secondary:
            sec_type, sec_desc = secondary[0]
            # Make it flow as second sentence
            if sec_type in ["goalie_mismatch", "goalie_edge"]:
                sentences.append(sec_desc)
            elif sec_type in ["schedule_b2b", "rest_advantage"]:
                sentences.append(sec_desc)
            elif sec_type == "pdo_mismatch":
                sentences.append(sec_desc)

        return " ".join(sentences[:2])

    def _generate_detailed_rationale(
        self,
        pick: FinalPick,
        factors: list[tuple[str, str]],
    ) -> str:
        """Generate detailed multi-line rationale."""
        lines = [
            f"Pick: {pick.pick_team} vs {pick.opponent}",
            f"Tier: {pick.tier} | Confidence: {pick.model_probability:.1%} | Edge: +{pick.edge:.1%}",
            "",
            "Key Factors:",
        ]

        for i, (factor_type, description) in enumerate(factors[:5], 1):
            lines.append(f"  {i}. {description}")

        if pick.risk_flags:
            lines.extend([
                "",
                "Risk Flags:",
            ])
            for flag in pick.risk_flags:
                lines.append(f"  • {flag}")

        if pick.adjustments:
            lines.extend([
                "",
                "Adjustments Applied:",
            ])
            for adj in pick.adjustments:
                lines.append(f"  • {adj}")

        return "\n".join(lines)

    def generate_rationales_batch(
        self,
        picks: list[FinalPick],
        as_of_date: Optional[date] = None,
    ) -> dict[int, str]:
        """
        Generate rationales for multiple picks.

        Returns:
            Dict mapping game_id to short rationale.
        """
        rationales = {}

        for pick in picks:
            try:
                factors = self.generate_rationale(pick, as_of_date)
                rationales[pick.game_id] = factors.short_rationale
            except Exception as e:
                logger.warning(f"Could not generate rationale for {pick.game_id}: {e}")
                rationales[pick.game_id] = f"Edge: +{pick.edge:.1%} vs market"

        return rationales


# Scenario templates for common pick types
SCENARIO_TEMPLATES = {
    "goalie_mismatch": (
        "Goalie mismatch favors {pick_team} ({goalie} {gsax_diff:+.1f} GSAx advantage)"
    ),
    "schedule_spot": (
        "{opponent} in tough schedule spot ({schedule_detail})"
    ),
    "pdo_regression": (
        "PDO regression play: {direction} team {team} at {pdo:.0f}"
    ),
    "system_mismatch": (
        "System mismatch: {pick_team}'s {system_type} approach exploits {opponent}"
    ),
    "desperation": (
        "{team} in desperation mode, {points_back} points out of playoffs"
    ),
    "home_ice": (
        "Strong home ice advantage for {team} ({home_record})"
    ),
    "rest_advantage": (
        "Rest edge: {pick_team} with {rest_days} days rest vs fatigued {opponent}"
    ),
}


def generate_pick_rationale(
    pick: FinalPick,
    as_of_date: Optional[date] = None,
) -> str:
    """Convenience function to generate single pick rationale."""
    generator = RationaleGenerator()
    factors = generator.generate_rationale(pick, as_of_date)
    return factors.short_rationale


def generate_all_rationales(
    picks: list[FinalPick],
    as_of_date: Optional[date] = None,
) -> dict[int, str]:
    """Convenience function to generate rationales for all picks."""
    generator = RationaleGenerator()
    return generator.generate_rationales_batch(picks, as_of_date)
