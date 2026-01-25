"""Command Line Interface for NHL Predictor.

Provides commands for running predictions, viewing reports,
and checking system status.
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .selection.selector import PickSelector, select_picks
from .reporting.report_generator import ReportGenerator, generate_daily_report
from .reporting.rationale import RationaleGenerator
from .reporting.performance import PerformanceTracker, get_performance_summary
from .models.database import get_db
from .config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CLI:
    """NHL Predictor command line interface."""

    def __init__(self):
        """Initialize CLI."""
        self.selector = PickSelector()
        self.report_generator = ReportGenerator()
        self.rationale_generator = RationaleGenerator()
        self.performance_tracker = PerformanceTracker()

    def predict_today(
        self,
        output_format: str = "console",
        save: bool = False,
    ) -> int:
        """
        Generate predictions for today.

        Args:
            output_format: Output format (console, json, markdown).
            save: Whether to save report to file.

        Returns:
            Exit code (0 for success).
        """
        return self.predict_date(date.today(), output_format, save)

    def predict_date(
        self,
        game_date: date,
        output_format: str = "console",
        save: bool = False,
    ) -> int:
        """
        Generate predictions for a specific date.

        Args:
            game_date: Date to generate predictions for.
            output_format: Output format.
            save: Whether to save report.

        Returns:
            Exit code.
        """
        print(f"\nGenerating predictions for {game_date}...")

        try:
            # Get picks
            daily_picks = self.selector.select_daily_picks(game_date)

            if not daily_picks.picks:
                print("\nNo picks meet minimum requirements for this date.")
                print(f"Games analyzed: {daily_picks.total_games}")
                print(f"Games filtered: {daily_picks.games_filtered}")
                return 0

            # Generate rationales
            rationales = self.rationale_generator.generate_rationales_batch(
                daily_picks.picks, game_date
            )

            # Generate report
            report = self.report_generator.generate_report(daily_picks, rationales)

            # Output based on format
            if output_format == "json":
                output = self.report_generator.format_json(report)
            elif output_format == "markdown":
                output = self.report_generator.format_markdown(report)
            else:
                output = self.report_generator.format_console(report)

            print(output)

            # Save if requested
            if save:
                formats = ["json", "txt"] if output_format == "console" else [output_format]
                saved = self.report_generator.save_report(report, formats)
                for fmt, path in saved.items():
                    print(f"Saved {fmt} report to: {path}")

            return 0

        except Exception as e:
            logger.error(f"Error generating predictions: {e}")
            print(f"\nError: {e}")
            return 1

    def show_status(self) -> int:
        """
        Show system status and data freshness.

        Returns:
            Exit code.
        """
        print("\n" + "=" * 50)
        print("NHL PREDICTOR STATUS")
        print("=" * 50)

        # Database status
        try:
            db = get_db()
            with db.session_scope() as session:
                from .models.schema import Game, TeamDailyStats, GoalieStats

                games_count = session.query(Game).count()
                latest_game = session.query(Game).order_by(
                    Game.date.desc()
                ).first()

                stats_count = session.query(TeamDailyStats).count()
                latest_stats = session.query(TeamDailyStats).order_by(
                    TeamDailyStats.date.desc()
                ).first()

                goalie_count = session.query(GoalieStats).count()

            print("\nDATABASE STATUS")
            print(f"  Games: {games_count}")
            print(f"  Latest game: {latest_game.date if latest_game else 'None'}")
            print(f"  Team stats: {stats_count}")
            print(f"  Latest stats: {latest_stats.date if latest_stats else 'None'}")
            print(f"  Goalie records: {goalie_count}")

        except Exception as e:
            print(f"\nDatabase error: {e}")

        # Performance summary
        print("\nMODEL PERFORMANCE")
        try:
            summary = get_performance_summary("30d")
            print(f"  30-Day Record: {summary.wins}-{summary.losses}")
            print(f"  Win Rate: {summary.win_rate:.1%}")
            print(f"  ROI: {summary.roi:+.1f}%")
        except Exception as e:
            print(f"  Could not load performance: {e}")

        # Config
        print("\nCONFIGURATION")
        try:
            config = get_config()
            print(f"  Database: {config.database.path}")
            print(f"  Model weights: xGF={config.model.xgf_weight}, "
                  f"HDCF={config.model.hdcf_weight}, GSAx={config.model.gsax_weight}")
        except Exception as e:
            print(f"  Could not load config: {e}")

        print("\n" + "=" * 50)
        return 0

    def show_history(
        self,
        period: str = "30d",
        detailed: bool = False,
    ) -> int:
        """
        Show performance history.

        Args:
            period: Time period (7d, 30d, season).
            detailed: Show detailed breakdown.

        Returns:
            Exit code.
        """
        try:
            if detailed:
                report = self.performance_tracker.format_weekly_summary()
            else:
                summary = self.performance_tracker.get_performance_summary(period)
                report = self.performance_tracker.format_summary_report(summary)

            print(report)
            return 0

        except Exception as e:
            logger.error(f"Error loading history: {e}")
            print(f"\nError: {e}")
            return 1

    def run_backtest(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        output_file: Optional[str] = None,
    ) -> int:
        """
        Run historical backtest.

        Args:
            start_date: Start date for backtest.
            end_date: End date (defaults to yesterday).
            output_file: Optional file to save results.

        Returns:
            Exit code.
        """
        if end_date is None:
            end_date = date.today()

        print(f"\nRunning backtest from {start_date} to {end_date}...")
        print("This may take a while...")

        try:
            from .testing.backtest import run_backtest

            results = run_backtest(start_date, end_date)

            # Print summary
            print("\n" + "=" * 50)
            print("BACKTEST RESULTS")
            print("=" * 50)
            print(f"\nPeriod: {start_date} to {end_date}")
            print(f"Games analyzed: {results['total_games']}")
            print(f"Picks made: {results['total_picks']}")
            print(f"Win Rate: {results['win_rate']:.1%}")
            print(f"ROI: {results['roi']:+.1f}%")
            print(f"Brier Score: {results['brier_score']:.4f}")

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                print(f"\nResults saved to: {output_file}")

            return 0

        except ImportError:
            print("\nBacktest module not available.")
            return 1
        except Exception as e:
            logger.error(f"Backtest error: {e}")
            print(f"\nError: {e}")
            return 1

    def update_data(self) -> int:
        """
        Run data update jobs.

        Returns:
            Exit code.
        """
        print("\nUpdating data sources...")

        from .fetchers import (
            NHLAPIFetcher,
            NaturalStatTrickScraper,
            DailyFaceoffScraper,
        )

        errors = []

        # Update schedule
        print("  Fetching NHL schedule...")
        try:
            nhl = NHLAPIFetcher()
            nhl.fetch_schedule(date.today())
        except Exception as e:
            errors.append(f"NHL schedule: {e}")
            logger.warning(f"Failed to fetch NHL schedule: {e}")

        # Update stats
        print("  Fetching team stats...")
        try:
            nst = NaturalStatTrickScraper()
            nst.fetch_team_stats()
        except Exception as e:
            errors.append(f"Team stats: {e}")
            logger.warning(f"Failed to fetch team stats: {e}")

        # Update goalies
        print("  Fetching goalie info...")
        try:
            df = DailyFaceoffScraper()
            df.fetch_starting_goalies()
        except Exception as e:
            errors.append(f"Goalie info: {e}")
            logger.warning(f"Failed to fetch goalie info: {e}")

        # Update prediction outcomes
        print("  Updating prediction outcomes...")
        try:
            updated = self.performance_tracker.update_results()
            print(f"    Updated {updated} predictions")
        except Exception as e:
            errors.append(f"Prediction outcomes: {e}")
            logger.warning(f"Failed to update prediction outcomes: {e}")

        if errors:
            print(f"\nData update completed with {len(errors)} warning(s):")
            for err in errors:
                print(f"  - {err}")
            return 0  # Still return success, just with warnings

        print("\nData update complete!")
        return 0


def parse_date(date_str: str) -> date:
    """Parse date string in various formats."""
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {date_str}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="nhl-predict",
        description="NHL Game Prediction Tool",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # predict today
    today_parser = subparsers.add_parser(
        "today",
        help="Generate predictions for today",
    )
    today_parser.add_argument(
        "--format", "-f",
        choices=["console", "json", "markdown"],
        default="console",
        help="Output format",
    )
    today_parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="Save report to file",
    )

    # predict date
    date_parser = subparsers.add_parser(
        "date",
        help="Generate predictions for specific date",
    )
    date_parser.add_argument(
        "date",
        type=str,
        help="Date (YYYY-MM-DD)",
    )
    date_parser.add_argument(
        "--format", "-f",
        choices=["console", "json", "markdown"],
        default="console",
        help="Output format",
    )
    date_parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="Save report to file",
    )

    # status
    subparsers.add_parser(
        "status",
        help="Show system status",
    )

    # history
    history_parser = subparsers.add_parser(
        "history",
        help="Show performance history",
    )
    history_parser.add_argument(
        "--period", "-p",
        choices=["7d", "30d", "season"],
        default="30d",
        help="Time period",
    )
    history_parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="Show detailed breakdown",
    )

    # backtest
    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Run historical backtest",
    )
    backtest_parser.add_argument(
        "start_date",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    backtest_parser.add_argument(
        "--end", "-e",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD)",
    )
    backtest_parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file for results",
    )

    # update
    subparsers.add_parser(
        "update",
        help="Update data sources",
    )

    # Parse args
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cli = CLI()

    # Execute command
    if args.command == "today":
        return cli.predict_today(args.format, args.save)

    elif args.command == "date":
        try:
            game_date = parse_date(args.date)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        return cli.predict_date(game_date, args.format, args.save)

    elif args.command == "status":
        return cli.show_status()

    elif args.command == "history":
        return cli.show_history(args.period, args.detailed)

    elif args.command == "backtest":
        try:
            start = parse_date(args.start_date)
            end = parse_date(args.end) if args.end else None
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        return cli.run_backtest(start, end, args.output)

    elif args.command == "update":
        return cli.update_data()

    return 0


if __name__ == "__main__":
    sys.exit(main())
