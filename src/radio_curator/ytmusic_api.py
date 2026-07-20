"""YouTube Music API utilities for creating playlists and searching tracks."""

import os
import sys
import argparse
import json
import unicodedata
import pathlib

from typing import List, Tuple, Optional, Dict, Any, cast

from ytmusicapi import YTMusic
from ytmusicapi.setup import setup


# Simple in-memory cache for search results
_search_cache: Dict[str, str] = {}
# File to persist cache between runs in a proper cache directory
XDG_CACHE_HOME = os.environ.get(
    "XDG_CACHE_HOME", os.path.join(pathlib.Path.home(), ".cache")
)
CACHE_DIR = os.path.join(XDG_CACHE_HOME, "radio_curator")
CACHE_FILE = os.path.join(CACHE_DIR, "search_cache.json")
HEADERS_FILE = os.path.join(CACHE_DIR, "headers_auth.json")


def load_cache() -> None:
    """Load search cache from file"""
    # pylint: disable-next=global-statement
    global _search_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _search_cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            _search_cache = {}


def save_cache() -> None:
    """Save search cache to file"""
    try:
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_search_cache, f)
    except OSError:
        pass


def get_ytmusic() -> YTMusic:
    """Get YTMusic instance with authentication"""
    if os.path.exists(HEADERS_FILE):
        return YTMusic(HEADERS_FILE)
    print(f"Headers authentication file not found at {HEADERS_FILE}")
    print(
        "Please create headers_auth.json using YTMusic.setup() "
        "or place it in the cache directory"
    )
    sys.exit(1)


def find_playlist(ytmusic: YTMusic, title: str) -> Optional[str]:
    """Check if a playlist with the given title already exists"""
    try:
        playlists = ytmusic.get_library_playlists(limit=None)
        for playlist in playlists:
            if playlist["title"] == title:
                return playlist["playlistId"]
    # ytmusicapi doesn't document specific exceptions; handle broadly
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error checking for existing playlist: {e}", file=sys.stderr)

    return None


def create_or_find_playlist(
    ytmusic: YTMusic, title: str, description: str = "", privacy_status: str = "PRIVATE"
) -> Tuple[str, bool]:
    """Create a new playlist or return existing one. Returns (playlist_id, was_created)"""
    existing_id = find_playlist(ytmusic, title)
    if existing_id:
        return existing_id, False

    result: str = cast(str, ytmusic.create_playlist(title, description, privacy_status))
    return result, True


def add_tracks_to_playlist(
    ytmusic: YTMusic, playlist_id: str, video_ids: List[str]
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Add multiple tracks to a YouTube playlist in batch"""
    responses: List[Dict[str, Any]] = []
    errors: List[Tuple[str, str]] = []

    try:
        # ytmusicapi can add multiple tracks at once
        response = ytmusic.add_playlist_items(playlist_id, video_ids)
        responses.append(cast(Dict[str, Any], response))
    # ytmusicapi doesn't document specific exceptions; handle broadly
    except Exception:  # pylint: disable=broad-exception-caught
        # If batch add fails, try adding individually
        for video_id in video_ids:
            try:
                response = ytmusic.add_playlist_items(playlist_id, [video_id])
                responses.append(cast(Dict[str, Any], response))
            except Exception as individual_e:  # pylint: disable=broad-exception-caught
                errors.append((video_id, str(individual_e)))

    return responses, errors


def search_track(
    ytmusic: YTMusic, query: str, expected_artist: str = "", expected_title: str = ""
) -> Optional[Dict[str, Any]]:
    """Search for a music track on YouTube Music and return the best match with details"""
    try:
        # Search for songs first
        songs_results = ytmusic.search(query, filter="songs", limit=5)

        # If we have expected artist/title, try to find exact match in songs
        if expected_artist and expected_title and songs_results:
            exact_match = find_best_match(songs_results, expected_artist, expected_title)
            if exact_match:
                return exact_match
        # If no exact match in songs, try videos
        videos_results = ytmusic.search(query, filter="videos", limit=5)

        if expected_artist and expected_title and videos_results:
            exact_match = find_best_match(videos_results, expected_artist, expected_title)
            if exact_match:
                return exact_match

        # If no exact match found in either songs or videos, fall back to first result
        # Prefer songs over videos if both have results
        if songs_results:
            return songs_results[0]
        if videos_results:
            return videos_results[0]

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Search error for query '{query}': {e}", file=sys.stderr)

    return None


def find_best_match(
    results: List[Dict[str, Any]], expected_artist: str, expected_title: str
) -> Optional[Dict[str, Any]]:
    """Find the best matching result based on artist and title"""
    expected_artist_norm = normalize_text(expected_artist)
    expected_title_norm = normalize_text(expected_title)

    for result in results:
        # Get artist names from the result
        artists = result.get("artists", [])
        artist_names = [normalize_text(artist.get("name", "")) for artist in artists]

        # Get title from result
        result_title_norm = normalize_text(result.get("title", ""))

        # Check if expected artist matches any of the result artists (more flexible
        # matching)
        artist_match = any(
            expected_artist_norm == artist_name
            or expected_artist_norm in artist_name
            or artist_name in expected_artist_norm
            for artist_name in artist_names
        )

        # For video results, also check if artist appears in the title
        # This handles cases where videos have "Artist - Song" format in title
        if not artist_match:
            artist_match = expected_artist_norm in result_title_norm

        # Check if expected title matches result title (more flexible matching)
        title_match = (
            expected_title_norm == result_title_norm
            or expected_title_norm in result_title_norm
            or result_title_norm in expected_title_norm
        )

        # If both match, this is a good result
        if artist_match and title_match:
            return result

    return None


def normalize_text(text: str) -> str:
    """Normalize text for comparison by removing accents and normalizing quotes"""
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # First handle special characters that don't decompose with NFD
    special_char_replacements = {
        "ł": "l",
        "đ": "d",  # U+0111 LATIN SMALL LETTER D WITH STROKE
        "ħ": "h",
        "ŧ": "t",
        "ø": "o",
        "æ": "ae",
        "œ": "oe",
        "ß": "ss",
        "ð": "d",  # U+00F0 LATIN SMALL LETTER ETH
        "þ": "th",
        "ŋ": "ng",
        "Ł": "L",  # U+0141 LATIN CAPITAL LETTER L WITH STROKE
        "Đ": "D",  # U+0110 LATIN CAPITAL LETTER D WITH STROKE
        "Ħ": "H",  # U+0126 LATIN CAPITAL LETTER H WITH STROKE
        "Ŧ": "T",  # U+0166 LATIN CAPITAL LETTER T WITH STROKE
        "Ø": "O",  # U+00D8 LATIN CAPITAL LETTER O WITH STROKE
        "Æ": "AE",  # U+00C6 LATIN CAPITAL LETTER AE
        "Œ": "OE",  # U+0152 LATIN CAPITAL LIGATURE OE
        "Ð": "D",  # U+00D0 LATIN CAPITAL LETTER ETH
        "Þ": "TH",  # U+00DE LATIN CAPITAL LETTER THORN
        "Ŋ": "NG",  # U+014A LATIN CAPITAL LETTER ENG
    }

    for special_char, replacement in special_char_replacements.items():
        text = text.replace(special_char, replacement)

    # Normalize unicode characters (remove accents)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")

    # More comprehensive normalization of quotes and apostrophes
    # Replace all apostrophe-like characters with standard ASCII apostrophe
    apostrophe_chars = [
        "’",
    ]

    for apostrophe in apostrophe_chars:
        text = text.replace(apostrophe, "'")

    # Replace quote characters
    quote_chars = [
        '"',  # U+201C LEFT DOUBLE QUOTATION MARK
        '"',  # U+201D RIGHT DOUBLE QUOTATION MARK
    ]

    for quote in quote_chars:
        text = text.replace(quote, '"')

    return text


def get_artist_names(result: Dict[str, Any]) -> str:
    """Extract artist names from a search result"""
    artists = result.get("artists", [])
    if artists:
        return ", ".join(artist.get("name", "") for artist in artists)
    return "Unknown Artist"


def search_track_with_cache(
    ytmusic: YTMusic, query: str, expected_artist: str = "", expected_title: str = ""
) -> Optional[Dict[str, Any]]:
    """Search for a track with caching"""
    # Load cache if not already loaded
    if not _search_cache:
        load_cache()

    # For caching, we'll use just the video ID but return full result
    if query in _search_cache:
        video_id = _search_cache[query]
        # We need to search again to get full details, but this should be fast
        # since we know the video exists
        result = search_track(ytmusic, query, expected_artist, expected_title)
        if result and result.get("videoId") == video_id:
            return result

    result = search_track(ytmusic, query, expected_artist, expected_title)
    if result:
        video_id = result.get("videoId")
        if video_id is not None:
            _search_cache[query] = video_id
        save_cache()
    return result


def main() -> None:
    """Entry point for YTMusic API command-line tools."""
    # TODO(#42): add a subcommand to add a track ID to a playlist ID
    parser = argparse.ArgumentParser(description="YouTube Music API tools")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup subcommand for initial authentication
    _ = subparsers.add_parser("setup", help="Setup YTMusic authentication")

    # Create playlist subcommand
    create_parser = subparsers.add_parser(
        "create-playlist", help="Create a new YouTube playlist"
    )
    create_parser.add_argument("name", help="Name of the playlist to create")
    create_parser.add_argument(
        "description", nargs="?", default="", help="Description of the playlist"
    )
    create_parser.add_argument(
        "privacy",
        nargs="?",
        default="PRIVATE",
        choices=["PUBLIC", "PRIVATE", "UNLISTED"],
        help="Privacy status of the playlist",
    )

    # Search track subcommand
    search_parser = subparsers.add_parser(
        "search-track", help="Search for a track and return its ID"
    )
    search_parser.add_argument("query", help="Search query for the track")

    # Add track to playlist subcommand
    add_parser = subparsers.add_parser("add-track", help="Add a track to a playlist")
    add_parser.add_argument("playlist_id", help="ID of the playlist to add track to")
    add_parser.add_argument("video_id", help="ID of the video/track to add")

    # Print tracks subcommand (without creating a playlist)
    print_parser = subparsers.add_parser(
        "print-tracks", help="Print tracks without creating a playlist"
    )
    print_parser.add_argument("query", help="Search query for tracks (comma-separated)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "setup":
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        print("Setting up YTMusic authentication...")
        print(f"Headers file will be saved to: {HEADERS_FILE}")
        setup(filepath=HEADERS_FILE)
        print("Setup complete!")
        return

    ytmusic = get_ytmusic()

    if args.command == "create-playlist":
        playlist_id, was_created = create_or_find_playlist(
            ytmusic, args.name, args.description, args.privacy
        )
        if was_created:
            print(f"Created playlist: {args.name}")
        else:
            print(f"Found existing playlist: {args.name}")
        print(f"Playlist ID: {playlist_id}")

    elif args.command == "search-track":
        result = search_track_with_cache(ytmusic, args.query)
        if result:
            video_id = result.get("videoId")
            title = result.get("title", "Unknown")
            artist = get_artist_names(result)
            print(f"Found track ID: {video_id}")
            print(f"Title: {title}")
            print(f"Artist: {artist}")
        else:
            print("No track found for the given query")

    # Add track to playlist subcommand
    elif args.command == "add-track":
        responses, errors = add_tracks_to_playlist(
            ytmusic, args.playlist_id, [args.video_id]
        )
        if errors:
            print(
                "Error adding track "
                f"{args.video_id} to playlist {args.playlist_id}: "
                f"{errors[0][1]}"
            )
        else:
            print(f"Added track {args.video_id} to playlist {args.playlist_id}")
            if responses:
                print(f"Response: {responses[0]}")

    elif args.command == "print-tracks":
        # Split the query string by commas and search for each track
        queries = [q.strip() for q in args.query.split(",")]
        print(f"Searching for {len(queries)} tracks...")

        for i, query in enumerate(queries, 1):
            print(f"\nTrack {i}/{len(queries)}: {query}")
            result = search_track_with_cache(ytmusic, query)

            if result:
                video_id = result.get("videoId")
                title = result.get("title", "Unknown")
                artist = get_artist_names(result)
                print(f"Found: {query}")
                print(f"Video ID: {video_id}")
                print(f"Title: {title}")
                print(f"Artist: {artist}")
                print(f"YouTube URL: https://www.youtube.com/watch?v={video_id}")
            else:
                print(f"Not found: {query}")


if __name__ == "__main__":
    main()
