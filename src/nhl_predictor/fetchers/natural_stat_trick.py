"""Natural Stat Trick scraper for advanced team statistics.

Scrapes team-level advanced metrics from naturalstattrick.com.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from io import StringIO

import pandas as pd

from .base import BaseFetcher
from ..utils.team_mapping import normalize_team_name_safe

logger = logging.getLogger(__name__)


@dataclass
class TeamAdvancedStats:
    """Advanced team statistics from Natural Stat Trick."""

    team: str
    games_played: int

    # Possession metrics
    cf: float  # Corsi For
    ca: float  # Corsi Against
    cf_pct: float  # Corsi For %

    ff: float  # Fenwick For
    fa: float  # Fenwick Against
    ff_pct: float  # Fenwick For %

    sf: float  # Shots For
    sa: float  # Shots Against
    sf_pct: float  # Shots For %

    # Expected Goals
    xgf: float  # Expected Goals For
    xga: float  # Expected Goals Against
    xgf_pct: float  # Expected Goals For %

    # Scoring Chances
    scf: float  # Scoring Chances For
    sca: float  # Scoring Chances Against
    scf_pct: float  # Scoring Chances For %

    # High Danger Chances
    hdcf: float  # High Danger Chances For
    hdca: float  # High Danger Chances Against
    hdcf_pct: float  # High Danger Chances For %

    # Luck metrics
    sh_pct: float  # Shooting %
    sv_pct: float  # Save %
    pdo: float  # PDO (Sh% + Sv%)

    # Goals
    gf: int  # Goals For
    ga: int  # Goals Against


class NSTScraper(BaseFetcher):
    """Scraper for Natural Stat Trick team statistics."""

    BASE_URL = "https://www.naturalstattrick.com"
    RATE_LIMIT_DELAY = 3  # Be respectful of NST

    def __init__(self):
        super().__init__(source_name="natural_stat_trick")

    @property
    def base_url(self) -> str:
        """Return the base URL (for compatibility)."""
        return self.BASE_URL

    def fetch(self, **kwargs) -> list[TeamAdvancedStats]:
        """Fetch team stats from NST."""
        return self.fetch_team_stats(**kwargs)

    def fetch_team_stats(
        self,
        season: str = "20252026",
        situation: str = "5v5",
        score_state: str = "all",
        save_to_db: bool = True,
    ) -> list[TeamAdvancedStats]:
        """
        Fetch team-level advanced statistics from Natural Stat Trick.

        Args:
            season: Season in format "20252026".
            situation: Game situation (5v5, all, pp, pk).
            score_state: Score state (all, leading, trailing, close).
            save_to_db: Whether to save to database.

        Returns:
            List of TeamAdvancedStats objects.
        """
        # Map situation to NST parameter
        sit_map = {
            "5v5": "5v5",
            "all": "all",
            "pp": "pp",
            "pk": "pk",
            "ev": "ev",
        }
        sit = sit_map.get(situation, "5v5")

        # Build URL
        url = f"{self.BASE_URL}/teamtable.php"
        params = {
            "fromseason": season,
            "thruseason": season,
            "stype": 2,  # Regular season
            "sit": sit,
            "score": score_state,
            "rate": "n",  # Not rate stats
            "team": "all",
            "loc": "B",  # Both home and away
            "gpf": "410",  # Games per filter
            "fd": "",
            "td": "",
        }

        start_time = datetime.now()
        stats = []

        try:
            logger.info(f"Fetching NST team stats for {season} ({situation})")

            response = self.fetch_url(url, params=params)
            html = response.text

            # Parse HTML tables with pandas
            stats = self._parse_team_table(html)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and stats:
                self._save_stats_to_db(stats, situation)

            self.log_fetch(
                fetch_type=f"team_stats_{situation}",
                status="success",
                records_fetched=len(stats),
                duration_seconds=duration,
            )

            logger.info(f"Fetched stats for {len(stats)} teams")
            return stats

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type=f"team_stats_{situation}",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch NST stats: {e}")
            raise

    def _parse_team_table(self, html: str) -> list[TeamAdvancedStats]:
        """Parse team statistics from HTML table."""
        stats = []

        try:
            # Use pandas to parse all tables
            tables = pd.read_html(StringIO(html))

            if not tables:
                logger.warning("No tables found in NST response")
                return stats

            # The main team stats table is usually the first one
            df = tables[0]

            # Clean column names
            df.columns = [str(col).strip() for col in df.columns]

            # Process each team row
            for _, row in df.iterrows():
                team_stats = self._parse_team_row(row)
                if team_stats:
                    stats.append(team_stats)

        except Exception as e:
            logger.error(f"Failed to parse NST table: {e}")

        return stats

    def _parse_team_row(self, row: pd.Series) -> Optional[TeamAdvancedStats]:
        """Parse a single team row from the table."""
        try:
            # Get team name and normalize
            team_name = str(row.get("Team", ""))
            team_code = normalize_team_name_safe(team_name)

            if not team_code:
                logger.debug(f"Could not normalize team: {team_name}")
                return None

            # Helper to safely get float values
            def get_float(col: str, default: float = 0.0) -> float:
                try:
                    val = row.get(col, default)
                    if pd.isna(val):
                        return default
                    return float(val)
                except (ValueError, TypeError):
                    return default

            def get_int(col: str, default: int = 0) -> int:
                try:
                    val = row.get(col, default)
                    if pd.isna(val):
                        return default
                    return int(float(val))
                except (ValueError, TypeError):
                    return default

            # Map common column name variations
            col_mappings = {
                "CF": ["CF", "Corsi For"],
                "CA": ["CA", "Corsi Against"],
                "CF%": ["CF%", "Corsi %"],
                "FF": ["FF", "Fenwick For"],
                "FA": ["FA", "Fenwick Against"],
                "FF%": ["FF%", "Fenwick %"],
                "SF": ["SF", "Shots For"],
                "SA": ["SA", "Shots Against"],
                "SF%": ["SF%", "Shots %"],
                "xGF": ["xGF", "Expected Goals For"],
                "xGA": ["xGA", "Expected Goals Against"],
                "xGF%": ["xGF%", "Expected Goals %"],
                "SCF": ["SCF", "Scoring Chances For"],
                "SCA": ["SCA", "Scoring Chances Against"],
                "SCF%": ["SCF%", "Scoring Chances %"],
                "HDCF": ["HDCF", "High Danger Chances For"],
                "HDCA": ["HDCA", "High Danger Chances Against"],
                "HDCF%": ["HDCF%", "High Danger Chances %"],
                "Sh%": ["Sh%", "SH%", "Shooting %"],
                "Sv%": ["Sv%", "SV%", "Save %"],
                "PDO": ["PDO"],
                "GF": ["GF", "Goals For"],
                "GA": ["GA", "Goals Against"],
                "GP": ["GP", "Games"],
            }

            def find_col_value(key: str, as_int: bool = False) -> float:
                """Find value using possible column names."""
                for col_name in col_mappings.get(key, [key]):
                    if col_name in row.index:
                        if as_int:
                            return get_int(col_name)
                        return get_float(col_name)
                return 0

            return TeamAdvancedStats(
                team=team_code,
                games_played=int(find_col_value("GP", as_int=True)),
                cf=find_col_value("CF"),
                ca=find_col_value("CA"),
                cf_pct=find_col_value("CF%"),
                ff=find_col_value("FF"),
                fa=find_col_value("FA"),
                ff_pct=find_col_value("FF%"),
                sf=find_col_value("SF"),
                sa=find_col_value("SA"),
                sf_pct=find_col_value("SF%"),
                xgf=find_col_value("xGF"),
                xga=find_col_value("xGA"),
                xgf_pct=find_col_value("xGF%"),
                scf=find_col_value("SCF"),
                sca=find_col_value("SCA"),
                scf_pct=find_col_value("SCF%"),
                hdcf=find_col_value("HDCF"),
                hdca=find_col_value("HDCA"),
                hdcf_pct=find_col_value("HDCF%"),
                sh_pct=find_col_value("Sh%"),
                sv_pct=find_col_value("Sv%"),
                pdo=find_col_value("PDO"),
                gf=int(find_col_value("GF", as_int=True)),
                ga=int(find_col_value("GA", as_int=True)),
            )

        except Exception as e:
            logger.warning(f"Failed to parse team row: {e}")
            return None

    def _save_stats_to_db(self, stats: list[TeamAdvancedStats], situation: str) -> None:
        """Save team stats to database."""
        from ..models.database import get_db
        from ..models.schema import TeamDailyStats

        today = date.today()
        source = f"nst_{situation}"

        db = get_db()
        with db.session_scope() as session:
            for team_stats in stats:
                # Check for existing record
                existing = session.query(TeamDailyStats).filter(
                    TeamDailyStats.date == today,
                    TeamDailyStats.team == team_stats.team,
                    TeamDailyStats.source == source,
                ).first()

                if existing:
                    # Update existing
                    existing.cf_pct = team_stats.cf_pct
                    existing.ff_pct = team_stats.ff_pct
                    existing.sf_pct = team_stats.sf_pct
                    existing.xgf = team_stats.xgf
                    existing.xga = team_stats.xga
                    existing.xgf_pct = team_stats.xgf_pct
                    existing.scf = team_stats.scf
                    existing.sca = team_stats.sca
                    existing.scf_pct = team_stats.scf_pct
                    existing.hdcf = team_stats.hdcf
                    existing.hdca = team_stats.hdca
                    existing.hdcf_pct = team_stats.hdcf_pct
                    existing.pdo = team_stats.pdo
                    existing.shooting_pct = team_stats.sh_pct
                    existing.save_pct = team_stats.sv_pct
                    existing.games_played = team_stats.games_played
                else:
                    # Create new
                    record = TeamDailyStats(
                        date=today,
                        team=team_stats.team,
                        cf_pct=team_stats.cf_pct,
                        ff_pct=team_stats.ff_pct,
                        sf_pct=team_stats.sf_pct,
                        xgf=team_stats.xgf,
                        xga=team_stats.xga,
                        xgf_pct=team_stats.xgf_pct,
                        scf=team_stats.scf,
                        sca=team_stats.sca,
                        scf_pct=team_stats.scf_pct,
                        hdcf=team_stats.hdcf,
                        hdca=team_stats.hdca,
                        hdcf_pct=team_stats.hdcf_pct,
                        pdo=team_stats.pdo,
                        shooting_pct=team_stats.sh_pct,
                        save_pct=team_stats.sv_pct,
                        games_played=team_stats.games_played,
                        source=source,
                    )
                    session.add(record)

        logger.debug(f"Saved NST stats for {len(stats)} teams")


def fetch_team_stats(season: str = "20252026", situation: str = "5v5") -> list[TeamAdvancedStats]:
    """Convenience function to fetch team stats."""
    with NSTScraper() as scraper:
        return scraper.fetch_team_stats(season=season, situation=situation)
