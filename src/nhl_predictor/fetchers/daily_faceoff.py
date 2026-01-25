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
from ..utils.team_mapping import normalize_team_name_safe, TEAM_FULL_NAMES

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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        })

    @property
    def base_url(self) -> str:
        """Return the base URL (for compatibility)."""
        return self.BASE_URL

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

        # Try multiple parsing strategies

        # Strategy 1: Look for matchup containers with team logos/names
        matchups = soup.select(".starting-goalies-matchup, .matchup, [class*='matchup']")
        if matchups:
            for matchup in matchups:
                parsed = self._parse_matchup_container(matchup)
                goalies.extend(parsed)
            if goalies:
                return goalies

        # Strategy 2: Look for individual goalie cards
        goalie_cards = soup.select(".goalie-card, .starter-card, [class*='goalie']")
        if goalie_cards:
            for card in goalie_cards:
                goalie = self._parse_goalie_card(card)
                if goalie:
                    goalies.append(goalie)
            if goalies:
                return goalies

        # Strategy 3: Parse from divs that contain team images and player links
        # Daily Faceoff often has team logos as images with alt text
        team_sections = soup.find_all("div", recursive=True)
        current_team = None

        for div in team_sections:
            # Look for team logo images
            img = div.find("img", alt=True)
            if img:
                alt_text = img.get("alt", "")
                team_code = normalize_team_name_safe(alt_text, log_warning=False)
                if team_code:
                    current_team = team_code

            # Look for player name links near team
            if current_team:
                links = div.find_all("a", href=lambda x: x and "players" in x)
                for link in links:
                    name = link.get_text(strip=True)
                    if self._looks_like_goalie_name(name):
                        # Check confirmation status
                        status = self._determine_status_from_context(div)

                        goalie = GoalieStart(
                            team=current_team,
                            goalie_name=name,
                            opponent="",
                            confirmation_status=status,
                            game_time=None,
                            record=None,
                            gaa=None,
                            save_pct=None,
                        )

                        # Avoid duplicates
                        if not any(g.team == current_team and g.goalie_name == name for g in goalies):
                            goalies.append(goalie)
                            logger.debug(f"Found goalie: {name} for {current_team} ({status})")

        # Strategy 4: Table-based parsing
        if not goalies:
            tables = soup.find_all("table")
            for table in tables:
                table_goalies = self._parse_goalie_table(table)
                goalies.extend(table_goalies)

        return goalies

    def _parse_matchup_container(self, container) -> list[GoalieStart]:
        """Parse a matchup container that contains two teams."""
        goalies = []

        # Look for team sections within the matchup
        teams_found = []

        # Find all images (usually team logos)
        images = container.find_all("img", alt=True)
        for img in images:
            alt = img.get("alt", "")
            team_code = normalize_team_name_safe(alt, log_warning=False)
            if team_code and team_code not in teams_found:
                teams_found.append(team_code)

        # Find all player links
        player_links = container.find_all("a", href=lambda x: x and "player" in str(x).lower())

        for i, team in enumerate(teams_found[:2]):  # Max 2 teams per matchup
            # Try to find corresponding goalie
            if i < len(player_links):
                name = player_links[i].get_text(strip=True)
                if self._looks_like_goalie_name(name):
                    status = self._determine_status_from_context(container)
                    goalies.append(GoalieStart(
                        team=team,
                        goalie_name=name,
                        opponent=teams_found[1-i] if len(teams_found) > 1 else "",
                        confirmation_status=status,
                        game_time=None,
                        record=None,
                        gaa=None,
                        save_pct=None,
                    ))

        return goalies

    def _parse_goalie_card(self, card) -> Optional[GoalieStart]:
        """Parse a goalie card element."""
        try:
            # Extract team from image alt or class
            team_code = None

            # Try image alt text
            img = card.find("img", alt=True)
            if img:
                team_code = normalize_team_name_safe(img.get("alt", ""), log_warning=False)

            # Try class names containing team abbreviations
            if not team_code:
                classes = " ".join(card.get("class", []))
                for code in TEAM_FULL_NAMES.keys():
                    if code.lower() in classes.lower():
                        team_code = code
                        break

            # Try text content
            if not team_code:
                for text in card.stripped_strings:
                    team_code = normalize_team_name_safe(text, log_warning=False)
                    if team_code:
                        break

            if not team_code:
                return None

            # Extract goalie name from player link
            goalie_name = None
            player_link = card.find("a", href=lambda x: x and "player" in str(x).lower())
            if player_link:
                goalie_name = player_link.get_text(strip=True)

            # Try finding name from text that looks like a name
            if not goalie_name:
                for text in card.stripped_strings:
                    if self._looks_like_goalie_name(text):
                        goalie_name = text
                        break

            if not goalie_name:
                return None

            # Determine confirmation status
            status = self._determine_status_from_context(card)

            # Extract stats if present
            record, gaa, save_pct = self._extract_goalie_stats(card)

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
            logger.debug(f"Failed to parse goalie card: {e}")
            return None

    def _parse_goalie_table(self, table) -> list[GoalieStart]:
        """Parse goalies from a table structure."""
        goalies = []
        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            team_code = None
            goalie_name = None
            record = None
            gaa = None
            save_pct = None

            for cell in cells:
                # Skip header cells
                if cell.name == "th":
                    continue

                # Look for team in images
                img = cell.find("img", alt=True)
                if img and not team_code:
                    team_code = normalize_team_name_safe(img.get("alt", ""), log_warning=False)

                # Look for player links
                link = cell.find("a", href=lambda x: x and "player" in str(x).lower())
                if link and not goalie_name:
                    name = link.get_text(strip=True)
                    if self._looks_like_goalie_name(name):
                        goalie_name = name

                # Extract text for stats
                text = cell.get_text(strip=True)

                # Skip stat labels
                if text in ["W-L-OTL:", "GAA:", "SV%:", "SO:"]:
                    continue

                # Parse stats values
                if re.match(r"^\d+-\d+-\d+$", text):
                    record = text
                elif re.match(r"^\d\.\d+$", text):
                    val = float(text)
                    if val < 1:
                        save_pct = val
                    elif val < 5:
                        gaa = val
                elif re.match(r"^0\.\d+$", text):
                    save_pct = float(text)

            if team_code and goalie_name:
                status = self._determine_status_from_context(row)
                goalies.append(GoalieStart(
                    team=team_code,
                    goalie_name=goalie_name,
                    opponent="",
                    confirmation_status=status,
                    game_time=None,
                    record=record,
                    gaa=gaa,
                    save_pct=save_pct,
                ))

        return goalies

    def _looks_like_goalie_name(self, text: str) -> bool:
        """Check if text looks like a player name."""
        if not text or len(text) < 3:
            return False

        # Skip stat labels and values
        if text in ["W-L-OTL:", "GAA:", "SV%:", "SO:", "Confirmed", "Expected", "Likely"]:
            return False
        if re.match(r"^\d", text):  # Starts with number
            return False
        if re.match(r"^0?\.\d+$", text):  # Save percentage
            return False

        # Name pattern: First Last, First M. Last, J. Last, etc.
        name_patterns = [
            r"^[A-Z][a-z]+\s+[A-Z][a-z'-]+$",  # John Smith
            r"^[A-Z][a-z]+\s+[A-Z]\.\s*[A-Z][a-z'-]+$",  # John A. Smith
            r"^[A-Z]\.\s*[A-Z][a-z'-]+$",  # J. Smith
            r"^[A-Z][a-z]+-[A-Z][a-z]+\s+[A-Z][a-z'-]+$",  # Jean-Claude Smith
        ]

        for pattern in name_patterns:
            if re.match(pattern, text):
                return True

        return False

    def _determine_status_from_context(self, element) -> str:
        """Determine goalie confirmation status from context."""
        # Get all text from element and parents
        context_text = ""

        # Check element itself
        if hasattr(element, "get_text"):
            context_text = element.get_text(strip=True).lower()

        # Check CSS classes
        classes = ""
        if hasattr(element, "get"):
            classes = " ".join(element.get("class", [])).lower()

        # Check parent classes too
        parent = element.parent if hasattr(element, "parent") else None
        if parent and hasattr(parent, "get"):
            classes += " " + " ".join(parent.get("class", [])).lower()

        # Determine status
        if "confirmed" in context_text or "confirmed" in classes:
            return "confirmed"
        elif "expected" in context_text or "expected" in classes:
            return "expected"
        elif "likely" in context_text or "likely" in classes:
            return "expected"
        elif "unconfirmed" in context_text or "unconfirmed" in classes:
            return "unconfirmed"

        # Check for checkmark or green indicators
        if "✓" in context_text or "check" in classes or "green" in classes:
            return "confirmed"

        # Default to expected (most goalies listed are expected to start)
        return "expected"

    def _extract_goalie_stats(self, element) -> tuple:
        """Extract goalie stats (record, GAA, SV%) from element."""
        record = None
        gaa = None
        save_pct = None

        text = element.get_text(strip=True) if hasattr(element, "get_text") else ""

        # Look for record pattern (W-L-OTL)
        record_match = re.search(r"(\d+-\d+-\d+)", text)
        if record_match:
            record = record_match.group(1)

        # Look for GAA (usually 2.XX or 3.XX)
        gaa_match = re.search(r"(\d\.\d{2})\s*(?:GAA)?", text)
        if gaa_match:
            val = float(gaa_match.group(1))
            if 1.5 < val < 5.0:  # Reasonable GAA range
                gaa = val

        # Look for SV% (usually .9XX)
        sv_match = re.search(r"(0?\.\d{3})\s*(?:SV%)?", text)
        if sv_match:
            val = float(sv_match.group(1))
            if 0.85 < val < 0.98:  # Reasonable SV% range
                save_pct = val

        return record, gaa, save_pct

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
