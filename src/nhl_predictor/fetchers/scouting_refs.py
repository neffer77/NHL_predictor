"""Scouting The Refs scraper for referee assignments and statistics.

Scrapes daily referee assignments from scoutingtherefs.com.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup

from .base import BaseFetcher
from ..utils.team_mapping import normalize_team_name_safe

logger = logging.getLogger(__name__)


@dataclass
class RefereeProfile:
    """Referee statistics and profile."""

    name: str
    games_officiated: int
    home_win_pct: float
    penalties_per_game: float
    home_bias: float  # Deviation from league average
    penalty_deviation: float  # Deviation from league average


@dataclass
class GameRefereeAssignment:
    """Referee assignment for a specific game."""

    date: date
    home_team: str
    away_team: str
    referees: list[str]
    linesmen: list[str]
    referee_profiles: list[RefereeProfile]


class ScoutingRefsScraper(BaseFetcher):
    """Scraper for Scouting The Refs data."""

    BASE_URL = "https://scoutingtherefs.com"

    # League averages for calculating bias
    LEAGUE_AVG_HOME_WIN_PCT = 0.54
    LEAGUE_AVG_PENALTIES_PER_GAME = 7.5

    # Rate limit
    RATE_LIMIT_DELAY = 3

    def __init__(self):
        super().__init__(source_name="scouting_refs")
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })

    def fetch(self, **kwargs) -> list[GameRefereeAssignment]:
        """Fetch referee assignments."""
        return self.fetch_assignments(**kwargs)

    def fetch_assignments(
        self,
        game_date: Optional[date] = None,
        save_to_db: bool = True,
    ) -> list[GameRefereeAssignment]:
        """
        Fetch referee assignments for a specific date.

        Args:
            game_date: Date to fetch assignments for (defaults to today).
            save_to_db: Whether to save to database.

        Returns:
            List of game referee assignments.
        """
        if game_date is None:
            game_date = date.today()

        start_time = datetime.now()
        assignments = []

        try:
            logger.info(f"Fetching referee assignments for {game_date}")

            # Scouting The Refs URL structure for NHL
            date_str = game_date.strftime("%Y-%m-%d")
            url = f"{self.BASE_URL}/nhl-referees-and-linesmen-for-{date_str}/"

            # Try alternative URL formats
            urls_to_try = [
                url,
                f"{self.BASE_URL}/nhl-referee-assignments/",
                f"{self.BASE_URL}/todays-officials/",
            ]

            html = None
            for try_url in urls_to_try:
                try:
                    response = self.fetch_url(try_url)
                    if response.status_code == 200:
                        html = response.text
                        break
                except Exception:
                    continue

            if html:
                assignments = self._parse_assignments(html, game_date)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and assignments:
                self._save_assignments_to_db(assignments)

            self.log_fetch(
                fetch_type="referee_assignments",
                status="success" if assignments else "partial",
                records_fetched=len(assignments),
                duration_seconds=duration,
            )

            logger.info(f"Fetched {len(assignments)} referee assignments")
            return assignments

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="referee_assignments",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch referee assignments: {e}")
            raise

    def _parse_assignments(
        self,
        html: str,
        game_date: date,
    ) -> list[GameRefereeAssignment]:
        """Parse referee assignments from HTML."""
        assignments = []
        soup = BeautifulSoup(html, "lxml")

        # Look for game assignment blocks
        # Common patterns: tables, divs with game info
        game_blocks = soup.select(
            ".game-officials, .matchup, .game-row, "
            "table.officials, [class*='assignment']"
        )

        if not game_blocks:
            # Try to find tables with game info
            tables = soup.find_all("table")
            for table in tables:
                parsed = self._parse_officials_table(table, game_date)
                assignments.extend(parsed)
            return assignments

        for block in game_blocks:
            assignment = self._parse_game_block(block, game_date)
            if assignment:
                assignments.append(assignment)

        return assignments

    def _parse_game_block(
        self,
        block,
        game_date: date,
    ) -> Optional[GameRefereeAssignment]:
        """Parse a game block for referee assignments."""
        try:
            # Extract teams
            team_elems = block.select(".team, [class*='team']")
            teams = []
            for elem in team_elems:
                text = elem.get_text(strip=True)
                team_code = normalize_team_name_safe(text)
                if team_code:
                    teams.append(team_code)

            # Also try to extract from text patterns
            if len(teams) < 2:
                block_text = block.get_text()
                # Look for "Team @ Team" or "Team vs Team" pattern
                match = re.search(
                    r"([A-Za-z ]+?)\s*(?:@|vs\.?|at)\s*([A-Za-z ]+)",
                    block_text
                )
                if match:
                    away = normalize_team_name_safe(match.group(1).strip())
                    home = normalize_team_name_safe(match.group(2).strip())
                    if away and home:
                        teams = [away, home]

            if len(teams) < 2:
                return None

            away_team, home_team = teams[0], teams[1]

            # Extract referees
            referees = []
            ref_elems = block.select(
                ".referee, .ref, [class*='referee'], [class*='official']"
            )
            for elem in ref_elems:
                name = elem.get_text(strip=True)
                if name and self._is_name(name):
                    referees.append(name)

            # If no refs found, search for name patterns
            if not referees:
                block_text = block.get_text()
                # Look for "Referee:" or "Refs:" followed by names
                ref_match = re.search(
                    r"Referees?:?\s*([A-Z][a-z]+ [A-Z][a-z]+(?:,\s*[A-Z][a-z]+ [A-Z][a-z]+)*)",
                    block_text
                )
                if ref_match:
                    names = ref_match.group(1).split(",")
                    referees = [n.strip() for n in names if n.strip()]

            # Extract linesmen
            linesmen = []
            lines_elems = block.select(".linesman, [class*='linesman']")
            for elem in lines_elems:
                name = elem.get_text(strip=True)
                if name and self._is_name(name):
                    linesmen.append(name)

            # Build referee profiles (with default/estimated stats)
            profiles = [self._create_default_profile(ref) for ref in referees]

            return GameRefereeAssignment(
                date=game_date,
                home_team=home_team,
                away_team=away_team,
                referees=referees,
                linesmen=linesmen,
                referee_profiles=profiles,
            )

        except Exception as e:
            logger.debug(f"Failed to parse game block: {e}")
            return None

    def _parse_officials_table(
        self,
        table,
        game_date: date,
    ) -> list[GameRefereeAssignment]:
        """Parse a table containing officials information."""
        assignments = []

        rows = table.find_all("tr")
        current_game = None
        current_refs = []
        current_lines = []

        for row in rows:
            cells = row.find_all(["td", "th"])
            row_text = row.get_text(strip=True)

            # Check if this is a game header row
            match = re.search(
                r"([A-Za-z ]+?)\s*(?:@|vs\.?|at)\s*([A-Za-z ]+)",
                row_text
            )
            if match:
                # Save previous game if exists
                if current_game:
                    assignments.append(GameRefereeAssignment(
                        date=game_date,
                        home_team=current_game[1],
                        away_team=current_game[0],
                        referees=current_refs,
                        linesmen=current_lines,
                        referee_profiles=[
                            self._create_default_profile(r) for r in current_refs
                        ],
                    ))

                away = normalize_team_name_safe(match.group(1).strip())
                home = normalize_team_name_safe(match.group(2).strip())
                if away and home:
                    current_game = (away, home)
                    current_refs = []
                    current_lines = []
                continue

            # Check for referee/linesman rows
            if "referee" in row_text.lower():
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if self._is_name(text):
                        current_refs.append(text)
            elif "linesman" in row_text.lower() or "lines" in row_text.lower():
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if self._is_name(text):
                        current_lines.append(text)

        # Don't forget the last game
        if current_game:
            assignments.append(GameRefereeAssignment(
                date=game_date,
                home_team=current_game[1],
                away_team=current_game[0],
                referees=current_refs,
                linesmen=current_lines,
                referee_profiles=[
                    self._create_default_profile(r) for r in current_refs
                ],
            ))

        return assignments

    def _is_name(self, text: str) -> bool:
        """Check if text looks like a person's name."""
        if not text or len(text) < 5:
            return False
        # Name pattern: First Last or First M. Last
        return bool(re.match(
            r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+$",
            text.strip()
        ))

    def _create_default_profile(self, name: str) -> RefereeProfile:
        """Create a default referee profile (to be updated with actual stats)."""
        return RefereeProfile(
            name=name,
            games_officiated=0,
            home_win_pct=self.LEAGUE_AVG_HOME_WIN_PCT,
            penalties_per_game=self.LEAGUE_AVG_PENALTIES_PER_GAME,
            home_bias=0.0,
            penalty_deviation=0.0,
        )

    def _save_assignments_to_db(
        self,
        assignments: list[GameRefereeAssignment],
    ) -> None:
        """Save referee assignments to database."""
        from ..models.database import get_db
        from ..models.schema import Referee, RefereeAssignment

        db = get_db()
        with db.session_scope() as session:
            for assignment in assignments:
                # Save each referee
                for ref_profile in assignment.referee_profiles:
                    # Check if referee exists
                    existing = session.query(Referee).filter(
                        Referee.name == ref_profile.name
                    ).first()

                    if not existing:
                        ref = Referee(
                            name=ref_profile.name,
                            games_officiated=ref_profile.games_officiated,
                            home_win_pct=ref_profile.home_win_pct,
                            penalties_per_game=ref_profile.penalties_per_game,
                            home_bias=ref_profile.home_bias,
                            penalty_deviation=ref_profile.penalty_deviation,
                            bias_tag="neutral",
                            event_level="average",
                        )
                        session.add(ref)

                # Save assignment
                for ref_name in assignment.referees:
                    ref_assignment = RefereeAssignment(
                        date=assignment.date,
                        home_team=assignment.home_team,
                        away_team=assignment.away_team,
                        referee_name=ref_name,
                        role="referee",
                    )
                    session.add(ref_assignment)

                for linesman_name in assignment.linesmen:
                    ref_assignment = RefereeAssignment(
                        date=assignment.date,
                        home_team=assignment.home_team,
                        away_team=assignment.away_team,
                        referee_name=linesman_name,
                        role="linesman",
                    )
                    session.add(ref_assignment)

        logger.debug(f"Saved {len(assignments)} referee assignments")

    def get_bias_for_game(
        self,
        home_team: str,
        away_team: str,
        game_date: Optional[date] = None,
    ) -> dict:
        """
        Get referee bias information for a specific game.

        Args:
            home_team: Home team code.
            away_team: Away team code.
            game_date: Date of the game.

        Returns:
            Dict with bias information.
        """
        if game_date is None:
            game_date = date.today()

        assignments = self.fetch_assignments(game_date=game_date, save_to_db=False)

        for assignment in assignments:
            if assignment.home_team == home_team and assignment.away_team == away_team:
                # Calculate average bias across assigned referees
                if not assignment.referee_profiles:
                    return {"bias_tag": "neutral", "home_bias": 0.0}

                avg_home_bias = sum(
                    p.home_bias for p in assignment.referee_profiles
                ) / len(assignment.referee_profiles)

                avg_penalty = sum(
                    p.penalty_deviation for p in assignment.referee_profiles
                ) / len(assignment.referee_profiles)

                bias_tag = "neutral"
                if avg_home_bias > 0.05:
                    bias_tag = "home_friendly"
                elif avg_home_bias < -0.05:
                    bias_tag = "away_friendly"

                event_level = "average"
                if avg_penalty > 1.5:
                    event_level = "high"
                elif avg_penalty < -1.5:
                    event_level = "low"

                return {
                    "bias_tag": bias_tag,
                    "home_bias": avg_home_bias,
                    "penalty_deviation": avg_penalty,
                    "event_level": event_level,
                    "referees": assignment.referees,
                }

        return {"bias_tag": "neutral", "home_bias": 0.0}


def fetch_referee_assignments(
    game_date: Optional[date] = None,
) -> list[GameRefereeAssignment]:
    """Convenience function to fetch referee assignments."""
    with ScoutingRefsScraper() as scraper:
        return scraper.fetch_assignments(game_date=game_date)
