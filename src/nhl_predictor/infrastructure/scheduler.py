"""Scheduled Job Orchestrator.

Manages scheduling for all data fetching and prediction jobs
using APScheduler.
"""

import logging
from datetime import datetime, time
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent

from ..config import get_config

logger = logging.getLogger(__name__)


class JobResult:
    """Result of a job execution."""

    def __init__(
        self,
        job_id: str,
        success: bool,
        message: str = "",
        error: Optional[Exception] = None,
    ):
        self.job_id = job_id
        self.success = success
        self.message = message
        self.error = error
        self.timestamp = datetime.now()


class JobOrchestrator:
    """Orchestrates all scheduled jobs."""

    def __init__(self, blocking: bool = False):
        """
        Initialize job orchestrator.

        Args:
            blocking: Use blocking scheduler (for standalone mode).
        """
        self.config = get_config()

        if blocking:
            self.scheduler = BlockingScheduler()
        else:
            self.scheduler = BackgroundScheduler()

        self._job_results: dict[str, JobResult] = {}
        self._setup_listeners()

    def _setup_listeners(self):
        """Set up event listeners for job monitoring."""
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED,
        )
        self.scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR,
        )

    def _on_job_executed(self, event: JobExecutionEvent):
        """Handle successful job execution."""
        self._job_results[event.job_id] = JobResult(
            job_id=event.job_id,
            success=True,
            message="Completed successfully",
        )
        logger.info(f"Job {event.job_id} completed successfully")

    def _on_job_error(self, event: JobExecutionEvent):
        """Handle job execution error."""
        self._job_results[event.job_id] = JobResult(
            job_id=event.job_id,
            success=False,
            message=str(event.exception) if event.exception else "Unknown error",
            error=event.exception,
        )
        logger.error(
            f"Job {event.job_id} failed: {event.exception}",
            exc_info=event.exception,
        )

    def add_daily_job(
        self,
        job_id: str,
        func: Callable,
        hour: int,
        minute: int = 0,
        **kwargs,
    ) -> None:
        """
        Add a daily scheduled job.

        Args:
            job_id: Unique job identifier.
            func: Function to execute.
            hour: Hour to run (0-23).
            minute: Minute to run (0-59).
            **kwargs: Additional arguments for the function.
        """
        self.scheduler.add_job(
            func,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            name=job_id,
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace period
        )
        logger.info(f"Added daily job {job_id} at {hour:02d}:{minute:02d}")

    def add_interval_job(
        self,
        job_id: str,
        func: Callable,
        minutes: int = 60,
        start_hour: int = 10,
        end_hour: int = 19,
        **kwargs,
    ) -> None:
        """
        Add an interval job that runs during specific hours.

        Args:
            job_id: Unique job identifier.
            func: Function to execute.
            minutes: Interval in minutes.
            start_hour: Start hour for job window.
            end_hour: End hour for job window.
            **kwargs: Additional arguments.
        """
        def wrapper():
            now = datetime.now()
            if start_hour <= now.hour < end_hour:
                return func(**kwargs)
            else:
                logger.debug(f"Job {job_id} skipped - outside active hours")

        self.scheduler.add_job(
            wrapper,
            trigger=IntervalTrigger(minutes=minutes),
            id=job_id,
            name=job_id,
            replace_existing=True,
        )
        logger.info(
            f"Added interval job {job_id} every {minutes}min "
            f"({start_hour}:00-{end_hour}:00)"
        )

    def add_custom_job(
        self,
        job_id: str,
        func: Callable,
        trigger: str,
        **trigger_args,
    ) -> None:
        """
        Add a job with custom trigger.

        Args:
            job_id: Unique job identifier.
            func: Function to execute.
            trigger: Trigger type ("cron", "interval", "date").
            **trigger_args: Trigger-specific arguments.
        """
        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=job_id,
            replace_existing=True,
            **trigger_args,
        )
        logger.info(f"Added custom job {job_id}")

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not remove job {job_id}: {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not pause job {job_id}: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not resume job {job_id}: {e}")
            return False

    def run_job_now(self, job_id: str) -> bool:
        """
        Manually trigger a job to run immediately.

        Args:
            job_id: Job to run.

        Returns:
            True if job was triggered.
        """
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.modify(next_run_time=datetime.now())
                logger.info(f"Triggered immediate run of {job_id}")
                return True
            else:
                logger.warning(f"Job {job_id} not found")
                return False
        except Exception as e:
            logger.error(f"Error triggering job {job_id}: {e}")
            return False

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get status of a specific job."""
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        last_result = self._job_results.get(job_id)

        return {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time,
            "pending": job.pending,
            "last_run": last_result.timestamp if last_result else None,
            "last_success": last_result.success if last_result else None,
            "last_message": last_result.message if last_result else None,
        }

    def get_all_jobs(self) -> list[dict]:
        """Get status of all jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            status = self.get_job_status(job.id)
            if status:
                jobs.append(status)
        return jobs

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job scheduler started")

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Job scheduler stopped")

    def setup_default_jobs(self) -> None:
        """Set up all default scheduled jobs."""
        schedule_config = self.config.schedule

        # Parse time strings
        def parse_time(time_str: str) -> tuple[int, int]:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])

        # NHL Schedule fetch - 8:00 AM
        hour, minute = parse_time(schedule_config.schedule_fetch_time)
        self.add_daily_job(
            "fetch_nhl_schedule",
            self._job_fetch_schedule,
            hour=hour,
            minute=minute,
        )

        # NST Stats - 9:00 AM
        hour, minute = parse_time(schedule_config.nst_fetch_time)
        self.add_daily_job(
            "fetch_nst_stats",
            self._job_fetch_nst,
            hour=hour,
            minute=minute,
        )

        # MoneyPuck - 10:00 AM
        hour, minute = parse_time(schedule_config.moneypuck_fetch_time)
        self.add_daily_job(
            "fetch_moneypuck",
            self._job_fetch_moneypuck,
            hour=hour,
            minute=minute,
        )

        # Referee assignments - 12:00 PM
        hour, minute = parse_time(schedule_config.refs_fetch_time)
        self.add_daily_job(
            "fetch_refs",
            self._job_fetch_refs,
            hour=hour,
            minute=minute,
        )

        # Goalie check - every hour during game hours
        self.add_interval_job(
            "check_goalies",
            self._job_check_goalies,
            minutes=schedule_config.goalie_check_interval,
            start_hour=10,
            end_hour=19,
        )

        # Generate predictions - 2:00 PM
        hour, minute = parse_time(schedule_config.predictions_time)
        self.add_daily_job(
            "generate_predictions",
            self._job_generate_predictions,
            hour=hour,
            minute=minute,
        )

        # Update outcomes - 11:00 PM (after games complete)
        self.add_daily_job(
            "update_outcomes",
            self._job_update_outcomes,
            hour=23,
            minute=0,
        )

        logger.info("Default jobs configured")

    def _job_fetch_schedule(self) -> None:
        """Job: Fetch NHL schedule."""
        from ..fetchers.nhl_api import NHLAPIFetcher
        from datetime import date

        logger.info("Running: Fetch NHL schedule")
        fetcher = NHLAPIFetcher()
        fetcher.fetch_schedule(date.today())

    def _job_fetch_nst(self) -> None:
        """Job: Fetch Natural Stat Trick data."""
        from ..fetchers.natural_stat_trick import NaturalStatTrickScraper

        logger.info("Running: Fetch NST stats")
        scraper = NaturalStatTrickScraper()
        scraper.fetch_team_stats()

    def _job_fetch_moneypuck(self) -> None:
        """Job: Fetch MoneyPuck data."""
        from ..fetchers.moneypuck import MoneyPuckFetcher

        logger.info("Running: Fetch MoneyPuck data")
        fetcher = MoneyPuckFetcher()
        fetcher.fetch_simulations()

    def _job_fetch_refs(self) -> None:
        """Job: Fetch referee assignments."""
        from ..fetchers.scouting_refs import ScoutingTheRefsScraper

        logger.info("Running: Fetch referee assignments")
        scraper = ScoutingTheRefsScraper()
        scraper.fetch_daily_assignments()

    def _job_check_goalies(self) -> None:
        """Job: Check goalie status."""
        from ..fetchers.daily_faceoff import DailyFaceoffScraper

        logger.info("Running: Check goalie status")
        scraper = DailyFaceoffScraper()
        scraper.fetch_starting_goalies()

    def _job_generate_predictions(self) -> None:
        """Job: Generate daily predictions."""
        from ..selection.selector import PickSelector
        from ..reporting.report_generator import ReportGenerator
        from ..reporting.notifications import NotificationManager
        from datetime import date

        logger.info("Running: Generate predictions")

        selector = PickSelector()
        daily_picks = selector.select_daily_picks(date.today())

        if daily_picks.picks:
            # Generate report
            generator = ReportGenerator()
            report = generator.generate_report(daily_picks)

            # Save report
            generator.save_report(report)

            # Send notifications
            notifier = NotificationManager()
            notifier.send_daily_picks(report)

            logger.info(f"Generated {len(daily_picks.picks)} picks")
        else:
            logger.info("No picks generated for today")

    def _job_update_outcomes(self) -> None:
        """Job: Update prediction outcomes."""
        from ..reporting.performance import PerformanceTracker

        logger.info("Running: Update outcomes")
        tracker = PerformanceTracker()
        updated = tracker.update_results()
        logger.info(f"Updated {updated} prediction outcomes")


def create_orchestrator(blocking: bool = False) -> JobOrchestrator:
    """Create and configure a job orchestrator."""
    orchestrator = JobOrchestrator(blocking=blocking)
    orchestrator.setup_default_jobs()
    return orchestrator


def run_scheduler():
    """Run the scheduler in blocking mode."""
    orchestrator = create_orchestrator(blocking=True)
    try:
        logger.info("Starting scheduler in blocking mode...")
        orchestrator.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrupted")
        orchestrator.stop()
