from src.scrapers.github_trending import GitHubTrendingScraper
from src.scrapers.hackernews import HackerNewsScraper
from src.scrapers.indiehackers import IndieHackersScraper
from src.scrapers.producthunt import ProductHuntScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.trends import GoogleTrendsScraper

ALL_SCRAPERS = [
    HackerNewsScraper,
    ProductHuntScraper,
    RedditScraper,
    IndieHackersScraper,
    GoogleTrendsScraper,
    GitHubTrendingScraper,
]

__all__ = [
    "ALL_SCRAPERS",
    "HackerNewsScraper",
    "ProductHuntScraper",
    "RedditScraper",
    "IndieHackersScraper",
    "GoogleTrendsScraper",
    "GitHubTrendingScraper",
]
