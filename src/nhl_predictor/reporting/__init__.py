"""Reporting and User Interface modules for NHL predictions."""

from .report_generator import (
    ReportGenerator,
    PickReport,
    DailyReport,
    generate_daily_report,
)

from .rationale import (
    RationaleGenerator,
    RationaleFactors,
    generate_pick_rationale,
    generate_all_rationales,
)

from .performance import (
    PerformanceTracker,
    PerformanceRecord,
    TierPerformance,
    PerformanceSummary,
    get_performance_summary,
    format_performance_report,
)

from .notifications import (
    NotificationManager,
    NotificationConfig,
    NotificationChannel,
    EmailChannel,
    WebhookChannel,
    GoalieMonitor,
    send_daily_picks_notification,
    test_notifications,
)

__all__ = [
    # Report Generator
    "ReportGenerator",
    "PickReport",
    "DailyReport",
    "generate_daily_report",
    # Rationale
    "RationaleGenerator",
    "RationaleFactors",
    "generate_pick_rationale",
    "generate_all_rationales",
    # Performance
    "PerformanceTracker",
    "PerformanceRecord",
    "TierPerformance",
    "PerformanceSummary",
    "get_performance_summary",
    "format_performance_report",
    # Notifications
    "NotificationManager",
    "NotificationConfig",
    "NotificationChannel",
    "EmailChannel",
    "WebhookChannel",
    "GoalieMonitor",
    "send_daily_picks_notification",
    "test_notifications",
]
