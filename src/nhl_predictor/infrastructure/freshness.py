"""Data Freshness Monitor.

Tracks and alerts on data staleness issues across all data sources.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

from ..models.database import get_db
from ..models.schema import DataFetchLog, Game, TeamDailyStats, GoalieStats

logger = logging.getLogger(__name__)


class FreshnessStatus(Enum):
    """Data freshness status levels."""

    FRESH = "fresh"  # Within expected update window
    STALE = "stale"  # Older than expected but usable
    CRITICAL = "critical"  # Very old, may affect predictions
    MISSING = "missing"  # No data available


@dataclass
class SourceFreshness:
    """Freshness info for a data source."""

    source: str
    status: FreshnessStatus
    last_update: Optional[datetime]
    age_hours: float
    max_age_hours: float
    records_count: int
    message: str


@dataclass
class FreshnessReport:
    """Overall data freshness report."""

    timestamp: datetime
    overall_status: FreshnessStatus
    sources: list[SourceFreshness]
    warnings: list[str]
    can_generate_predictions: bool


class FreshnessMonitor:
    """Monitors data freshness across all sources."""

    # Maximum age thresholds (hours)
    MAX_AGE = {
        "nhl_schedule": 24,
        "team_stats": 24,
        "goalie_stats": 12,
        "referee_assignments": 24,
        "moneypuck": 24,
    }

    # Critical age thresholds (hours) - data too old to trust
    CRITICAL_AGE = {
        "nhl_schedule": 48,
        "team_stats": 48,
        "goalie_stats": 24,
        "referee_assignments": 48,
        "moneypuck": 48,
    }

    def __init__(self):
        """Initialize freshness monitor."""
        self.db = get_db()

    def check_all_sources(self) -> FreshnessReport:
        """
        Check freshness of all data sources.

        Returns:
            FreshnessReport with overall status.
        """
        sources = []
        warnings = []

        # Check each source
        sources.append(self._check_schedule_freshness())
        sources.append(self._check_team_stats_freshness())
        sources.append(self._check_goalie_freshness())
        sources.append(self._check_fetch_log("referee_assignments"))
        sources.append(self._check_fetch_log("moneypuck"))

        # Determine overall status
        statuses = [s.status for s in sources]

        if FreshnessStatus.CRITICAL in statuses:
            overall = FreshnessStatus.CRITICAL
            can_predict = False
        elif FreshnessStatus.MISSING in statuses:
            overall = FreshnessStatus.MISSING
            can_predict = False
        elif FreshnessStatus.STALE in statuses:
            overall = FreshnessStatus.STALE
            can_predict = True
        else:
            overall = FreshnessStatus.FRESH
            can_predict = True

        # Generate warnings
        for source in sources:
            if source.status in [FreshnessStatus.STALE, FreshnessStatus.CRITICAL]:
                warnings.append(
                    f"{source.source}: {source.message} "
                    f"(last update: {source.age_hours:.1f}h ago)"
                )

        return FreshnessReport(
            timestamp=datetime.now(),
            overall_status=overall,
            sources=sources,
            warnings=warnings,
            can_generate_predictions=can_predict,
        )

    def _check_schedule_freshness(self) -> SourceFreshness:
        """Check NHL schedule data freshness."""
        source = "nhl_schedule"

        with self.db.session_scope() as session:
            # Get most recent game date
            latest = session.query(Game).order_by(
                Game.date.desc()
            ).first()

            if not latest:
                return SourceFreshness(
                    source=source,
                    status=FreshnessStatus.MISSING,
                    last_update=None,
                    age_hours=float("inf"),
                    max_age_hours=self.MAX_AGE[source],
                    records_count=0,
                    message="No schedule data available",
                )

            # Check fetch log for actual last update
            fetch_log = session.query(DataFetchLog).filter(
                DataFetchLog.source == "nhl_api",
                DataFetchLog.success == True,
            ).order_by(DataFetchLog.timestamp.desc()).first()

            last_update = fetch_log.timestamp if fetch_log else None
            age_hours = self._calculate_age_hours(last_update)

            count = session.query(Game).filter(
                Game.date >= date.today()
            ).count()

            status = self._determine_status(source, age_hours)

            return SourceFreshness(
                source=source,
                status=status,
                last_update=last_update,
                age_hours=age_hours,
                max_age_hours=self.MAX_AGE[source],
                records_count=count,
                message=self._get_status_message(status, age_hours),
            )

    def _check_team_stats_freshness(self) -> SourceFreshness:
        """Check team stats data freshness."""
        source = "team_stats"

        with self.db.session_scope() as session:
            latest = session.query(TeamDailyStats).order_by(
                TeamDailyStats.date.desc()
            ).first()

            if not latest:
                return SourceFreshness(
                    source=source,
                    status=FreshnessStatus.MISSING,
                    last_update=None,
                    age_hours=float("inf"),
                    max_age_hours=self.MAX_AGE[source],
                    records_count=0,
                    message="No team stats available",
                )

            # Estimate last update from latest data date
            last_update = datetime.combine(latest.date, datetime.min.time())
            age_hours = self._calculate_age_hours(last_update)

            count = session.query(TeamDailyStats).filter(
                TeamDailyStats.date == latest.date
            ).count()

            status = self._determine_status(source, age_hours)

            return SourceFreshness(
                source=source,
                status=status,
                last_update=last_update,
                age_hours=age_hours,
                max_age_hours=self.MAX_AGE[source],
                records_count=count,
                message=self._get_status_message(status, age_hours),
            )

    def _check_goalie_freshness(self) -> SourceFreshness:
        """Check goalie stats data freshness."""
        source = "goalie_stats"

        with self.db.session_scope() as session:
            latest = session.query(GoalieStats).order_by(
                GoalieStats.date.desc()
            ).first()

            if not latest:
                return SourceFreshness(
                    source=source,
                    status=FreshnessStatus.MISSING,
                    last_update=None,
                    age_hours=float("inf"),
                    max_age_hours=self.MAX_AGE[source],
                    records_count=0,
                    message="No goalie data available",
                )

            last_update = datetime.combine(latest.date, datetime.min.time())
            age_hours = self._calculate_age_hours(last_update)

            count = session.query(GoalieStats).filter(
                GoalieStats.date == latest.date
            ).count()

            status = self._determine_status(source, age_hours)

            return SourceFreshness(
                source=source,
                status=status,
                last_update=last_update,
                age_hours=age_hours,
                max_age_hours=self.MAX_AGE[source],
                records_count=count,
                message=self._get_status_message(status, age_hours),
            )

    def _check_fetch_log(self, source: str) -> SourceFreshness:
        """Check freshness from fetch log."""
        with self.db.session_scope() as session:
            fetch_log = session.query(DataFetchLog).filter(
                DataFetchLog.source == source,
                DataFetchLog.success == True,
            ).order_by(DataFetchLog.timestamp.desc()).first()

            if not fetch_log:
                return SourceFreshness(
                    source=source,
                    status=FreshnessStatus.MISSING,
                    last_update=None,
                    age_hours=float("inf"),
                    max_age_hours=self.MAX_AGE.get(source, 24),
                    records_count=0,
                    message=f"No {source} data has been fetched",
                )

            age_hours = self._calculate_age_hours(fetch_log.timestamp)
            status = self._determine_status(source, age_hours)

            return SourceFreshness(
                source=source,
                status=status,
                last_update=fetch_log.timestamp,
                age_hours=age_hours,
                max_age_hours=self.MAX_AGE.get(source, 24),
                records_count=fetch_log.records_fetched or 0,
                message=self._get_status_message(status, age_hours),
            )

    def _calculate_age_hours(self, timestamp: Optional[datetime]) -> float:
        """Calculate age in hours from timestamp."""
        if timestamp is None:
            return float("inf")

        delta = datetime.now() - timestamp
        return delta.total_seconds() / 3600

    def _determine_status(self, source: str, age_hours: float) -> FreshnessStatus:
        """Determine freshness status based on age."""
        max_age = self.MAX_AGE.get(source, 24)
        critical_age = self.CRITICAL_AGE.get(source, 48)

        if age_hours <= max_age:
            return FreshnessStatus.FRESH
        elif age_hours <= critical_age:
            return FreshnessStatus.STALE
        else:
            return FreshnessStatus.CRITICAL

    def _get_status_message(self, status: FreshnessStatus, age_hours: float) -> str:
        """Get human-readable status message."""
        if status == FreshnessStatus.FRESH:
            return "Data is current"
        elif status == FreshnessStatus.STALE:
            return f"Data is stale ({age_hours:.1f}h old)"
        elif status == FreshnessStatus.CRITICAL:
            return f"Data critically outdated ({age_hours:.1f}h old)"
        else:
            return "No data available"

    def get_confidence_modifier(self) -> float:
        """
        Get confidence modifier based on data freshness.

        Returns:
            Modifier between 0.8 and 1.0 to apply to predictions.
        """
        report = self.check_all_sources()

        if report.overall_status == FreshnessStatus.FRESH:
            return 1.0
        elif report.overall_status == FreshnessStatus.STALE:
            return 0.95
        elif report.overall_status == FreshnessStatus.CRITICAL:
            return 0.85
        else:
            return 0.0  # Cannot make predictions

    def format_status_report(self) -> str:
        """Format freshness status as text report."""
        report = self.check_all_sources()

        status_icons = {
            FreshnessStatus.FRESH: "✓",
            FreshnessStatus.STALE: "⚠",
            FreshnessStatus.CRITICAL: "✗",
            FreshnessStatus.MISSING: "○",
        }

        lines = [
            "",
            "═" * 60,
            "DATA FRESHNESS STATUS",
            f"Checked: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "═" * 60,
            "",
            f"Overall Status: {status_icons[report.overall_status]} {report.overall_status.value.upper()}",
            f"Can Generate Predictions: {'Yes' if report.can_generate_predictions else 'No'}",
            "",
            "─" * 60,
            "SOURCE DETAILS",
            "─" * 60,
        ]

        for source in report.sources:
            icon = status_icons[source.status]
            lines.append(
                f"  {icon} {source.source:20s} | "
                f"Age: {source.age_hours:5.1f}h / {source.max_age_hours:.0f}h max | "
                f"Records: {source.records_count}"
            )

        if report.warnings:
            lines.extend([
                "",
                "─" * 60,
                "WARNINGS",
                "─" * 60,
            ])
            for warning in report.warnings:
                lines.append(f"  ⚠ {warning}")

        lines.extend([
            "",
            "═" * 60,
        ])

        return "\n".join(lines)

    def should_alert(self) -> tuple[bool, list[str]]:
        """
        Check if freshness alert should be sent.

        Returns:
            Tuple of (should_alert, list of alert messages).
        """
        report = self.check_all_sources()

        if report.overall_status in [FreshnessStatus.CRITICAL, FreshnessStatus.MISSING]:
            return True, report.warnings

        # Also alert if multiple sources are stale
        stale_count = sum(
            1 for s in report.sources
            if s.status == FreshnessStatus.STALE
        )

        if stale_count >= 2:
            return True, report.warnings

        return False, []


def check_data_freshness() -> FreshnessReport:
    """Convenience function to check data freshness."""
    monitor = FreshnessMonitor()
    return monitor.check_all_sources()


def get_freshness_status() -> str:
    """Convenience function to get formatted freshness status."""
    monitor = FreshnessMonitor()
    return monitor.format_status_report()
