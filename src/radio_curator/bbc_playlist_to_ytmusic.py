import re
import sys
import time
import argparse
import json
from typing import List, Dict, Tuple, Any, cast, Optional

import requests  
from bs4 import BeautifulSoup, Tag

# Import the YouTube API functions from the same package
from .ytmusic_api import get_ytmusic, search_track_with_cache, create_or_find_playlist, add_tracks_to_playlist, get_artist_names, normalize_text


def parse_bbc_playlist(program_id: str) -> Tuple[str, List[Dict[str, str]], str, str]:
    """Scrape BBC programme page and extract playlist information"""
    url = f"https://www.bbc.co.uk/programmes/{program_id}"

    # Add headers to mimic a real browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching BBC page: {e}", file=sys.stderr)
        return "", [], "", ""

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove the orb-skip-links div to avoid parsing navigation elements
    skip_links = soup.find("div", class_="orb-skip-links")
    if skip_links and isinstance(skip_links, Tag):
        skip_links.decompose()

    # Extract title from the h1 tag
    title_element = soup.find("h1")
    playlist_title = (
        title_element.get_text(strip=True)
        if title_element
        else f"BBC Playlist {program_id}"
    )

    # Extract broadcast date from broadcast-event__date span
    broadcast_date = ""
    date_element = soup.find("span", class_="broadcast-event__date")
    if date_element:
        date_text = date_element.get_text(strip=True)
        # Parse date like "Sat 27 Dec 2025" and convert to ISO format
        try:
            from datetime import datetime
            # Remove day of week and parse
            date_parts = date_text.split()
            if len(date_parts) >= 4:
                # Format: "Sat 27 Dec 2025"
                day = date_parts[1]
                month = date_parts[2]
                year = date_parts[3]
                date_str = f"{day} {month} {year}"
                parsed_date = datetime.strptime(date_str, "%d %b %Y")
                broadcast_date = parsed_date.strftime("%Y-%m-%d")
        except Exception:
            # If parsing fails, leave broadcast_date empty
            pass

    # Extract description from synopsis-toggle__long div
    description = ""
    synopsis_long = soup.find("div", class_="synopsis-toggle__long")
    if synopsis_long and  isinstance(synopsis_long, Tag):
        # Find all p elements within the synopsis-toggle__long div
        p_elements = synopsis_long.find_all("p")
        if p_elements:
            # Extract text from all p elements and join with newlines
            description_parts = []
            for p in p_elements:
                # Get text content and clean up HTML entities
                text = p.get_text(separator=" ", strip=True)
                if text:
                    description_parts.append(text)
            description = "\n\n".join(description_parts)

    # Find the "Music Played" section and specifically look in segments-list div
    tracks: List[Dict[str, str]] = []
    music_section = soup.find("h2", string=re.compile(r"Music Played", re.I))
    if not music_section:
        raise ValueError("Expecting 'Music Played' section")

    # Find the segments-list container
    segments_list = soup.find("div", class_="segments-list")
    if not (segments_list and isinstance(segments_list, Tag)):
        raise ValueError("Expecting a track listing")

    # First, try to find tracks using the specific BBC music segment structure
    music_items = cast(Tag, segments_list).find_all("li", class_="segments-list__item--music")
    if not music_items:
        raise ValueError("Cannot find music tracks")

    for item in music_items:
        # Look for the segment__track div which contains artist and title
        track_div = item.find("div", class_="segment__track")
        if not track_div:
            continue

        # Find artist from span with class="artist"
        artist_span = track_div.find("span", class_="artist")
        artist = artist_span.get_text(strip=True) if artist_span else ""

        # Find title from the span inside p.no-margin that follows h3
        title_span = None
        h3_element = track_div.find("h3")
        if h3_element:
            # Find the p element that follows h3
            p_element = h3_element.find_next("p", class_="no-margin")
            if p_element:
                # Get the span inside the p element
                title_span = p_element.find("span")

        title = title_span.get_text(strip=True) if title_span else ""

        # Only add if we have both artist and title
        if artist and title and "live at maida vale" not in title.lower():
            tracks.append({"artist": artist, "title": title})

    if not tracks:
        raise ValueError("No music tracks found")

    return playlist_title, tracks, broadcast_date, description


def assess_match_quality(track: Dict[str, str], result: Dict[str, Any]) -> Tuple[str, bool, str]:
    """
    Compare a BBC track with a YouTube search result to determine match quality.
    Returns (status, include, notes).
    """
    yt_title = result.get('title', '')
    yt_artist = get_artist_names(result)
    
    expected_artist_norm = normalize_text(track['artist'])
    expected_title_norm = normalize_text(track['title'])
    
    yt_artist_norm = normalize_text(yt_artist)
    yt_title_norm = normalize_text(yt_title)
    
    # Check artist match (including checking list of artists in result)
    artist_match = (
        expected_artist_norm == yt_artist_norm or
        expected_artist_norm in yt_artist_norm or
        any(
            expected_artist_norm == normalize_text(artist.get('name', '')) or
            expected_artist_norm in normalize_text(artist.get('name', ''))
            for artist in result.get('artists', [])
        )
    )
    
    # Check title match
    title_match = (
        expected_title_norm == yt_title_norm or
        expected_title_norm in yt_title_norm
    )
    
    if artist_match and title_match:
        return "exact_match", True, ""
    elif artist_match or title_match:
        return "suspect_match", False, "Partial match - please verify"
    else:
        return "suspect_match", False, "Poor match - please verify"


def search_and_process_tracks(ytmusic: Any, tracks: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Search for tracks on YouTube Music and process them into draft format.
    Handles logging to stderr.
    """
    processed_tracks = []
    
    for i, track in enumerate(tracks, 1):
        search_query = f"{track['artist']} {track['title']}".strip()
        print(f"Searching for track {i}/{len(tracks)}: {search_query}", file=sys.stderr)
        
        result = search_track_with_cache(ytmusic, search_query, track['artist'], track['title'])
        
        if result:
            video_id = result.get('videoId')
            yt_title = result.get('title', '')
            yt_artist = get_artist_names(result)
            
            status, include, notes = assess_match_quality(track, result)
            
            # Log result
            if status == "exact_match":
                print(f"  Found: {video_id} - {yt_title} by {yt_artist}", file=sys.stderr)
            else:
                print(f"  Mismatch: Expected '{track['artist']} - {track['title']}' but found '{yt_title}' by '{yt_artist}'", file=sys.stderr)
            
            processed_tracks.append({
                "bbc_artist": track['artist'],
                "bbc_title": track['title'],
                "status": status,
                "video_id": video_id,
                "youtube_title": yt_title,
                "youtube_channel": yt_artist,
                "include": include,
                "notes": notes
            })
        else:
            print(f"  Not found: {track['artist']} - {track['title']}", file=sys.stderr)
            processed_tracks.append({
                "bbc_artist": track['artist'],
                "bbc_title": track['title'],
                "status": "not_found",
                "video_id": None,
                "youtube_title": None,
                "youtube_channel": None,
                "include": False,
                "notes": "Could not find on YouTube"
            })
        
        time.sleep(0.1)  # Rate limiting
        
    return processed_tracks


def create_youtube_playlist(title: str, tracks: List[Dict[str, str]], prefix: str = "", broadcast_date: str = "", description: str = "") -> List[Dict[str, str]]:
    """Create a YouTube playlist from BBC tracks (Direct Workflow)"""
    ytmusic = get_ytmusic()
    
    # Step 1: Search and process all tracks (in-memory draft)
    draft_tracks = search_and_process_tracks(ytmusic, tracks)
    
    # Step 2: Create playlist using the draft logic
    # Note: create_youtube_playlist_from_draft returns tracks that were NOT included
    not_included = create_youtube_playlist_from_draft(
        title, draft_tracks, prefix, broadcast_date, description
    )
    
    # Convert back to simple dict format for return value compatibility
    not_found_simple = []
    for track in not_included:
        not_found_simple.append({
            "artist": track.get("bbc_artist", ""),
            "title": track.get("bbc_title", "")
        })
        
    return not_found_simple


def create_youtube_playlist_from_draft(title: str, draft_tracks: List[Dict[str, Any]], prefix: str = "", broadcast_date: str = "", description: str = "") -> List[Dict[str, Any]]:
    """Create a YouTube playlist from draft tracks"""
    # Add prefix and date to title if specified
    if prefix:
        if broadcast_date:
            title = f"{prefix}-{broadcast_date}: {title}"
        else:
            title = f"{prefix}: {title}"
    
    # Get YTMusic instance
    ytmusic = get_ytmusic()
    
    # Create or find playlist
    playlist_id, was_created = create_or_find_playlist(ytmusic, title, description)
    if was_created:
        print(f"Created playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    else:
        print(f"Found existing playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    
    # Filter tracks marked for inclusion and have video IDs
    tracks_to_add = [track for track in draft_tracks if track.get('include', False) and track.get('video_id')]
    
    if not tracks_to_add:
        print("No tracks marked for inclusion", file=sys.stderr)
        return draft_tracks
    
    # Add tracks to playlist
    video_ids = [track['video_id'] for track in tracks_to_add]
    print(f"Adding {len(video_ids)} tracks to playlist...", file=sys.stderr)
    
    try:
        responses, errors = add_tracks_to_playlist(ytmusic, playlist_id, video_ids)
        
        if errors:
            print(f"Encountered {len(errors)} errors while adding tracks:", file=sys.stderr)
            for video_id, error in errors:
                track_info = next((track for track in tracks_to_add if track['video_id'] == video_id), None)
                if track_info:
                    track_name = f"{track_info['bbc_artist']} - {track_info['bbc_title']}"
                else:
                    track_name = f"Unknown track ({video_id})"
                print(f"  Failed to add {track_name}: {error}", file=sys.stderr)
        
        print(f"Successfully added {len(responses)} tracks to playlist", file=sys.stderr)
        
        # Return tracks that were not included
        not_included = [track for track in draft_tracks if not track.get('include', False)]
        return not_included
        
    except Exception as e:
        print(f"Error adding tracks to playlist: {e}", file=sys.stderr)
        
        # Fallback: Try adding individually (logic ported from original create_youtube_playlist)
        print("Falling back to individual track adding...", file=sys.stderr)
        failed_in_fallback = []
        
        for track in tracks_to_add:
            video_id = track['video_id']
            try:
                add_tracks_to_playlist(ytmusic, playlist_id, [video_id])
                print(f"  Added: {video_id}", file=sys.stderr)
            except Exception as inner_e:
                print(f"  Failed to add {video_id}: {inner_e}", file=sys.stderr)
                failed_in_fallback.append(track)
        
        # Return tracks not included + tracks that failed fallback
        not_included = [track for track in draft_tracks if not track.get('include', False)]
        return not_included + failed_in_fallback


def save_draft(title: str, tracks: List[Dict[str, str]], program_id: str, filename: str, broadcast_date: str = "", description: str = "") -> None:
    """Save playlist draft with search results to JSON file"""
    ytmusic = get_ytmusic()
    
    # Use shared processing logic
    draft_tracks = search_and_process_tracks(ytmusic, tracks)
    
    draft_data = {
        "playlist_title": title,
        "program_id": program_id,
        "broadcast_date": broadcast_date,
        "description": description,
        "tracks": draft_tracks,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(draft_data, f, indent=2, ensure_ascii=False)
    
    print(f"Draft saved to: {filename}", file=sys.stderr)


def load_draft(filename: str) -> Tuple[str, List[Dict[str, Any]], str, str]:
    """Load playlist draft from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            draft_data = json.load(f)
        
        title = draft_data.get("playlist_title", "")
        tracks = draft_data.get("tracks", [])
        broadcast_date = draft_data.get("broadcast_date", "")
        description = draft_data.get("description", "")
        
        return title, tracks, broadcast_date, description
    except Exception as e:
        print(f"Error loading draft file: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    # Create parser with subcommands
    parser = argparse.ArgumentParser(description='Convert BBC radio playlist to YouTube Music')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Draft subcommand - parse BBC playlist and save to file
    draft_parser = subparsers.add_parser('draft', help='Parse BBC playlist and save as draft file')
    draft_parser.add_argument('program_id', help='BBC program ID')
    draft_parser.add_argument('--output', '-o', help='Output filename for draft (default: program_id.json)')
    
    # Create YouTube playlist subcommand
    create_parser = subparsers.add_parser('create', help='Create a YouTube playlist from BBC playlist or draft file')
    create_group = create_parser.add_mutually_exclusive_group(required=True)
    create_group.add_argument('--program-id', help='BBC program ID')
    create_group.add_argument('--draft', help='Draft file to use')
    create_parser.add_argument('--prefix', '-p', help='Prefix to add to the playlist title')
    
    # Print tracks subcommand
    print_parser = subparsers.add_parser('print', help='Print tracks from BBC playlist or draft file without creating YouTube playlist')
    print_group = print_parser.add_mutually_exclusive_group(required=True)
    print_group.add_argument('--program-id', help='BBC program ID')
    print_group.add_argument('--draft', help='Draft file to use')
    
    args = parser.parse_args()
    
    # Default to 'create' command if none specified (for backward compatibility)
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'draft':
        # Parse BBC playlist and save as draft
        print("Fetching BBC playlist...", file=sys.stderr)
        title, tracks, broadcast_date, description = parse_bbc_playlist(args.program_id)

        if not title or not tracks:
            print("Failed to parse BBC playlist", file=sys.stderr)
            sys.exit(1)

        print(f"Found playlist: {title}", file=sys.stderr)
        print(f"Found {len(tracks)} tracks", file=sys.stderr)
        if broadcast_date:
            print(f"Broadcast date: {broadcast_date}", file=sys.stderr)
        if description:
            print(f"Description: {description[:100]}{'...' if len(description) > 100 else ''}", file=sys.stderr)

        # Determine output filename
        output_file = args.output if args.output else f"{args.program_id}.json"
        save_draft(title, tracks, args.program_id, output_file, broadcast_date, description)
        
        print(f"\nYou can now edit the draft file '{output_file}' to modify tracks before creating the playlist.", file=sys.stderr)
        print(f"To create the playlist, run: radio_curator bbc create --draft {output_file}", file=sys.stderr)

    elif args.command in ['create', 'print']:
        # Load playlist data from either BBC or draft file
        if hasattr(args, 'program_id') and args.program_id:
            print("Fetching BBC playlist...", file=sys.stderr)
            title, tracks, broadcast_date, description = parse_bbc_playlist(args.program_id)
            
            if not title or not tracks:
                print("Failed to parse BBC playlist", file=sys.stderr)
                sys.exit(1)

            print(f"Playlist: {title}", file=sys.stderr)
            print(f"Found {len(tracks)} tracks", file=sys.stderr)
            if broadcast_date:
                print(f"Broadcast date: {broadcast_date}", file=sys.stderr)
            if description:
                print(f"Description: {description[:100]}{'...' if len(description) > 100 else ''}", file=sys.stderr)

            if args.command == 'print':
                # Just print the tracks without creating a YouTube playlist
                print("\nTracks in playlist:")
                for i, track in enumerate(tracks, 1):
                    print(f"{i}. {track['artist']} - {track['title']}")
            else:
                # Create YouTube playlist and add tracks (old workflow)
                print("Creating YouTube playlist...", file=sys.stderr)
                not_found = create_youtube_playlist(title, tracks, args.prefix if hasattr(args, 'prefix') else "", broadcast_date, description)

                # Output unfound tracks to stdout
                if not_found:
                    print("\nTracks that could not be added (please add manually):", file=sys.stderr)
                    for track in not_found:
                        if isinstance(track, dict):
                            print(f"{track['artist']} - {track['title']}")
                        else:
                            print(track)
                else:
                    print("\nAll tracks were successfully added!", file=sys.stderr)
                    
        elif hasattr(args, 'draft') and args.draft:
            print(f"Loading draft from {args.draft}...", file=sys.stderr)
            title, draft_tracks, broadcast_date, description = load_draft(args.draft)
            
            if not title or not draft_tracks:
                print("Failed to load draft data", file=sys.stderr)
                sys.exit(1)

            print(f"Playlist: {title}", file=sys.stderr)
            print(f"Found {len(draft_tracks)} tracks", file=sys.stderr)
            if broadcast_date:
                print(f"Broadcast date: {broadcast_date}", file=sys.stderr)
            if description:
                print(f"Description: {description[:100]}{'...' if len(description) > 100 else ''}", file=sys.stderr)

            if args.command == 'print':
                # Just print the tracks without creating a YouTube playlist
                print("\nTracks in playlist:")
                for i, track in enumerate(draft_tracks, 1):
                    artist = track.get('bbc_artist', '')
                    title_track = track.get('bbc_title', '')
                    status = track.get('status', 'unknown')
                    include = track.get('include', False)
                    notes = track.get('notes', '')
                    
                    status_symbol = "✓" if include else "✗" if status == "not_found" else "?"
                    print(f"{i}. [{status_symbol}] {artist} - {title_track}")
                    if notes:
                        print(f"    Notes: {notes}")
                    if track.get('youtube_title'):
                        print(f"    YouTube: {track['youtube_title']} by {track.get('youtube_channel', 'Unknown')}")
            else:
                # Create YouTube playlist from draft (new workflow)
                print("Creating YouTube playlist from draft...", file=sys.stderr)
                not_included = create_youtube_playlist_from_draft(title, draft_tracks, args.prefix if hasattr(args, 'prefix') else "", broadcast_date, description)

                # Output tracks that were not included
                if not_included:
                    print("\nTracks that were not included:", file=sys.stderr)
                    for track in not_included:
                        artist = track.get('bbc_artist', '')
                        title_track = track.get('bbc_title', '')
                        notes = track.get('notes', '')
                        print(f"{artist} - {title_track}")
                        if notes:
                            print(f"  Reason: {notes}")
                else:
                    print("\nAll marked tracks were successfully added!", file=sys.stderr)
        else:
            print("Error: Must specify either --program-id or --draft", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
