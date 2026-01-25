"""Daily Faceoff scraper for starting goaltender information.

Scrapes confirmed starting goalies from dailyfaceoff.com.
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
class GoalieStart:
    """Starting goaltender information."""

    team: str
    goalie_name: str
    opponent: str
    confirmation_status: str  # confirmed, expected, unconfirmed
    game_time: Optional[str]
    record: Optional[str]  # W-L-OTL
    gaa: Optional[float]  # Goals Against Average
    save_pct: Optional[float]  # Save Percentage


class DailyFaceoffScraper(BaseFetcher):
    """Scraper for Daily Faceoff starting goaltenders."""

    BASE_URL = "https://www.dailyfaceoff.com"
    STARTING_GOALIES_URL = f"{BASE_URL}/starting-goalies"

    # Rate limit to be respectful
    RATE_LIMIT_DELAY = 3

    def __init__(self):
        super().__init__(source_name="daily_faceoff")
        # Update headers for this site
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })

    def fetch(self, **kwargs) -> list[GoalieStart]:
        """Fetch starting goalies."""
        return self.fetch_starting_goalies(**kwargs)

    def fetch_starting_goalies(
        self,
        save_to_db: bool = True,
    ) -> list[GoalieStart]:
        """
        Fetch today's starting goaltenders.

        Args:
            save_to_db: Whether to save to database.

        Returns:
            List of GoalieStart objects.
        """
        start_time = datetime.now()
        goalies = []

        try:
            logger.info("Fetching Daily Faceoff starting goalies")

            response = self.fetch_url(self.STARTING_GOALIES_URL)
            html = response.text

            goalies = self._parse_starting_goalies(html)

            duration = (datetime.now() - start_time).total_seconds()

            if save_to_db and goalies:
                self._save_goalies_to_db(goalies)

            self.log_fetch(
                fetch_type="starting_goalies",
                status="success",
                records_fetched=len(goalies),
                duration_seconds=duration,
            )

            logger.info(f"Fetched {len(goalies)} starting goalies")
            return goalies

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.log_fetch(
                fetch_type="starting_goalies",
                status="failed",
                error_message=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Failed to fetch starting goalies: {e}")
            raise

    def _parse_starting_goalies(self, html: str) -> list[GoalieStart]:
        """Parse starting goalies from HTML."""
        goalies = []
        soup = BeautifulSoup(html, "lxml")

        # Find all goalie cards/entries
        # Daily Faceoff structure varies, try multiple selectors
        goalie_cards = soup.select(".starting-goalies-card, .goalie-card, .matchup-card")

        if not goalie_cards:
            # Try alternative structure
            goalie_cards = soup.select("[class*='goalie'], [class*='starter']")

        if not goalie_cards:
            # Fall back to table structure
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    goalie = self._parse_table_row(row)
                    if goalie:
                        goalies.append(goalie)
            return goalies

        # Parse card-based structure
        for card in goalie_cards:
            goalie = self._parse_goalie_card(card)
            if goalie:
                goalies.append(goalie)

        return goalies

    def _parse_goalie_card(self, card) -> Optional[GoalieStart]:
        """Parse a goalie card element."""
        try:
            # Extract team name
            team_elem = card.select_one(
                ".team-name, .team, [class*='team'], img[alt]"
            )
            team_name = ""
            if team_elem:
                if team_elem.name == "img":
                    team_name = team_elem.get("alt", "")
                else:
                    team_name = team_elem.get_text(strip=True)

            team_code = normalize_team_name_safe(team_name)
            if not team_code:
                # Try to extract from parent or other elements
                for elem in card.select("[class*='team']"):
                    text = elem.get_text(strip=True)
                    team_code = normalize_team_name_safe(text)
                    if team_code:
                        break

            if not team_code:
                return None

            # Extract goalie name
            goalie_elem = card.select_one(
                ".goalie-name, .player-name, [class*='player'], a[href*='player']"
            )
            goalie_name = ""
            if goalie_elem:
                goalie_name = goalie_elem.get_text(strip=True)

            if not goalie_name:
                # Try to find any name-like element
                for elem in card.find_all(["a", "span", "div"]):
                    text = elem.get_text(strip=True)
                    # Look for name pattern (First Last)
                    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+", text):
                        goalie_name = text
                        break

            if not goalie_name:
                return None

            # Extract confirmation status
            status = "unconfirmed"
            status_elem = card.select_one(
                ".status, .confirmation, [class*='confirm'], [class*='status']"
            )
            if status_elem:
                status_text = status_elem.get_text(strip=True).lower()
                if "confirmed" in status_text or "✓" in status_text:
                    status = "confirmed"
                elif "expected" in status_text or "likely" in status_text:
                    status = "expected"

            # Also check for CSS classes indicating status
            card_classes = " ".join(card.get("class", []))
            if "confirmed" in card_classes.lower():
                status = "confirmed"
            elif "expected" in card_classes.lower():
                status = "expected"

            # Extract opponent
            opponent = ""
            opp_elem = card.select_one(
                ".opponent, .vs, [class*='opponent'], [class*='versus']"
            )
            if opp_elem:
                opp_text = opp_elem.get_text(strip=True)
                # Remove "vs" or "@" prefixes
                opp_text = re.sub(r"^(vs\.?|@)\s*", "", opp_text, flags=re.I)
                opponent = normalize_team_name_safe(opp_text) or ""

            # Extract stats if available
            record = None
            gaa = None
            save_pct = None

            stats_elem = card.select_one(".stats, .record, [class*='stats']")
            if stats_elem:
                stats_text = stats_elem.get_text(strip=True)

                # Look for record pattern (W-L-OTL)
                record_match = re.search(r"(\d+-\d+-\d+)", stats_text)
                if record_match:
                    record = record_match.group(1)

                # Look for GAA
                gaa_match = re.search(r"(\d+\.\d+)\s*GAA", stats_text, re.I)
                if gaa_match:
                    gaa = float(gaa_match.group(1))

                # Look for SV%
                sv_match = re.search(r"\.(\d{3})\s*SV%?", stats_text, re.I)
                if sv_match:
                    save_pct = float(f"0.{sv_match.group(1)}")

            # Extract game time if available
            game_time = None
            time_elem = card.select_one(".time, .game-time, [class*='time']")
            if time_elem:
                game_time = time_elem.get_text(strip=True)

            return GoalieStart(
                team=team_code,
                goalie_name=goalie_name,
                opponent=opponent,
                confirmation_status=status,
                game_time=game_time,
                record=record,
                gaa=gaa,
                save_pct=save_pct,
            )

        except Exception as e:
            logger.debug(f"Failed to parse goalie card: {e}")
            return None

    def _parse_table_row(self, row) -> Optional[GoalieStart]:
        """Parse a table row for goalie information."""
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                return None

            # Patterns to skip (stat labels and values)
            skip_patterns = [
                r"^W-L-OTL:?$",
                r"^GAA:?$",
                r"^SV%:?$",
                r"^SO:?$",
                r"^\d+-\d+-\d+$",  # Record pattern
                r"^\d+\.\d+$",     # Decimal numbers (GAA, SV%)
                r"^\d+$",          # Single numbers
                r"^0\.\d+$",       # Save percentage
            ]

            # Try to extract team and goalie name from cells
            team_code = None
            goalie_name = None
            record = None
            gaa = None
            save_pct = None

            for cell in cells:
                text = cell.get_text(strip=True)

                # Skip empty text
                if not text:
                    continue

                # Check if it matches skip patterns
                should_skip = False
                for pattern in skip_patterns:
                    if re.match(pattern, text, re.I):
                        should_skip = True
                        # But extract stats from these values
                        if re.match(r"^\d+-\d+-\d+$", text):
                            record = text
                        elif re.match(r"^\d+\.\d+$", text):
                            val = float(text)
                            if val < 1:  # Likely save percentage
                                save_pct = val
                            elif val < 5:  # Likely GAA
                                gaa = val
                        break

                if should_skip:
                    continue

                # Check if it's a team name (only for longer text that looks like team name)
                if not team_code and len(text) >= 3:
                    team_code = normalize_team_name_safe(text, log_warning=False)

                # Check if it looks like a player name (First Last or First M. Last)
                if not goalie_name and re.match(r"^[A-Z][a-z]+\.?\s+[A-Z][a-z'-]+", text):
                    goalie_name = text

            if not team_code or not goalie_name:
                return None

            # Check for confirmation indicators in the row
            row_text = row.get_text(strip=True).lower()
            status = "unconfirmed"
            if "confirmed" in row_text:
                status = "confirmed"
            elif "expected" in row_text or "likely" in row_text:
                status = "expected"

            return GoalieStart(
                team=team_code,
                goalie_name=goalie_name,
                opponent="",
                confirmation_status=status,
                game_time=None,
                record=record,
                gaa=gaa,
                save_pct=save_pct,
            )

        except Exception as e:
            logger.debug(f"Failed to parse table row: {e}")
            return None

    def _save_goalies_to_db(self, goalies: list[GoalieStart]) -> None:
        """Save goalie starts to database."""
        from ..models.database import get_db
        from ..models.schema import GoalieStats

        today = date.today()

        db = get_db()
        with db.session_scope() as session:
            for goalie in goalies:
                # Check for existing
                existing = session.query(GoalieStats).filter(
                    GoalieStats.date == today,
                    GoalieStats.player_name == goalie.goalie_name,
                    GoalieStats.team == goalie.team,
                ).first()

                if existing:
                    existing.is_starter = True
                    existing.confirmation_status = goalie.confirmation_status
                    if goalie.save_pct:
                        existing.save_pct = goalie.save_pct
                else:
                    record = GoalieStats(
                        date=today,
                        player_name=goalie.goalie_name,
                        team=goalie.team,
                        is_starter=True,
                        confirmation_status=goalie.confirmation_status,
                        save_pct=goalie.save_pct,
                        source="daily_faceoff",
                    )
                    session.add(record)

        logger.debug(f"Saved {len(goalies)} goalie starts to database")

    def get_confirmed_starters(self) -> dict[str, GoalieStart]:
        """
        Get only confirmed starting goalies.

        Returns:
            Dictionary mapping team code to confirmed goalie.
        """
        goalies = self.fetch_starting_goalies(save_to_db=False)
        return {
            g.team: g for g in goalies
            if g.confirmation_status == "confirmed"
        }

    def get_starter_for_team(self, team_code: str) -> Optional[GoalieStart]:
        """
        Get the starting goalie for a specific team.

        Args:
            team_code: 3-letter team code.

        Returns:
            GoalieStart if found, None otherwise.
        """
        goalies = self.fetch_starting_goalies(save_to_db=False)
        for goalie in goalies:
            if goalie.team == team_code.upper():
                return goalie
        return None


def fetch_starting_goalies() -> list[GoalieStart]:
    """Convenience function to fetch starting goalies."""
    with DailyFaceoffScraper() as scraper:
        return scraper.fetch_starting_goalies()


def get_confirmed_starters() -> dict[str, GoalieStart]:
    """Convenience function to get confirmed starters."""
    with DailyFaceoffScraper() as scraper:
        return scraper.get_confirmed_starters()
