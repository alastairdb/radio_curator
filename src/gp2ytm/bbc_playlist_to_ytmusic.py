import re
import sys
import time
import argparse
import json
import os
from typing import List, Dict, Tuple, Any, cast
from googleapiclient.discovery import Resource  # type: ignore

import requests  
from bs4 import BeautifulSoup, Tag

# Import the YouTube API functions from the same package
from .ytmusic_api import get_credentials, build, search_track_with_cache, create_or_find_playlist, add_tracks_to_playlist, get_video_details


def parse_bbc_playlist(program_id: str) -> Tuple[str, List[Dict[str, str]]]:
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
        return "", []

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

    # Find the "Music Played" section and specifically look in segments-list div
    tracks: List[Dict[str, str]] = []
    music_section = soup.find("h2", string=re.compile(r"Music Played", re.I))

    if music_section:
        # Find the segments-list container
        segments_list = soup.find("div", class_="segments-list")

        if segments_list and isinstance(segments_list, Tag):

            # First, try to find tracks using the specific BBC music segment structure
            music_items = cast(Tag, segments_list).find_all("li", class_="segments-list__item--music")
            
            if music_items:
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
            
            # If no tracks found with the specific structure, fall back to the generic approach

            # Only proceed with the fallback approach if no tracks were found
            if not tracks:
                track_elements = cast(Tag, segments_list).find_all(["li", "div"], recursive=False)

                for element in track_elements:
                    # Look for artist and track information
                    text_content = element.get_text(separator=" ", strip=True)

                    # Skip empty elements
                    if not text_content:
                        continue

                    # Try to extract artist and track from structured data
                    artist_element = element.find(["h3", "strong"])
                    artist = artist_element.get_text(strip=True) if artist_element else ""

                    # If we have structured data, parse it
                    if artist:
                        # Find siblings or other elements that might contain track info
                        for sibling in artist_element.next_siblings:
                            if hasattr(sibling, "get_text"):
                                track_candidate = sibling.get_text(strip=True)
                                if track_candidate and track_candidate != artist:
                                    tracks.append(
                                        {"artist": artist, "title": track_candidate}
                                    )
                                    break
                    else:
                        # Fallback: try to parse from text content
                        lines = [
                            line.strip()
                            for line in text_content.split("\n")
                            if line.strip()
                        ]
                        if len(lines) >= 2:
                            # Assume first line is artist, second is track
                            tracks.append({"artist": lines[0], "title": lines[1]})
                        elif len(lines) == 1 and " - " in lines[0]:
                            # Try to split on " - "
                            parts = lines[0].split(" - ", 1)
                            if len(parts) == 2:
                                tracks.append({"artist": parts[0], "title": parts[1]})

    # If we didn't find structured tracks, try a different approach within segments-list
    if not tracks:
        segments_list = soup.find("div", class_="segments-list")
        if segments_list and isinstance(segments_list, Tag):
            # Look for any list items that might contain track info
            list_items = segments_list.find_all("li")
            for item in list_items:
                text = item.get_text(separator=" ", strip=True)
                # Simple heuristic: look for patterns like "Artist Track" or "Artist - Track"
                if re.search(r"\w+\s+\w+", text) and len(text) > 5:
                    # Try to split on common separators
                    if " - " in text:
                        parts = text.split(" - ", 1)
                        tracks.append(
                            {"artist": parts[0].strip(), "title": parts[1].strip()}
                        )
                    elif " feat " in text.lower():
                        parts = text.split(" feat ", 1)
                        tracks.append(
                            {"artist": parts[0].strip(), "title": parts[1].strip()}
                        )
                    else:
                        # Just use the whole text as title, no artist
                        tracks.append({"artist": "", "title": text})

    return playlist_title, tracks

def create_youtube_playlist(title: str, tracks: List[Dict[str, str]], prefix: str = "") -> List[Dict[str, str]]:
    """Create a YouTube playlist from BBC tracks"""
    # Add prefix to title if specified
    if prefix:
        title = f"{prefix}: {title}"
    
    # Get YouTube credentials and service
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    # Create or find playlist
    playlist_id, was_created = create_or_find_playlist(youtube_service, title)
    if was_created:
        print(f"Created playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    else:
        print(f"Found existing playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    
    # Search for all tracks first
    track_search_results: List[Dict[str, Any]] = []
    not_found: List[Dict[str, str]] = []
    mismatched: List[Dict[str, Any]] = []
    
    for i, track in enumerate(tracks, 1):
        search_query = f"{track['artist']} {track['title']}".strip()
        print(f"Searching for track {i}/{len(tracks)}: {search_query}", file=sys.stderr)
        
        video_id = search_track_with_cache(youtube_service, search_query)
        if video_id:
            # Get video details to verify match
            video_details = get_video_details(youtube_service, video_id)
            if video_details:
                # Check if the returned video matches our search criteria
                yt_title = video_details.get('title', '').lower()
                yt_channel = video_details.get('channelTitle', '').lower()
                
                expected_artist = track['artist'].lower()
                expected_title = track['title'].lower()
                
                # Check if both artist and title are in the YouTube video details
                artist_match = expected_artist in yt_title or expected_artist in yt_channel
                title_match = expected_title in yt_title
                
                if artist_match and title_match:
                    track_search_results.append({
                        'track_info': track,
                        'video_id': video_id,
                        'search_query': search_query
                    })
                    print(f"  Found: {video_id} - {video_details.get('title')}", file=sys.stderr)
                else:
                    print(f"  Mismatch: Expected '{track['artist']} - {track['title']}' but found '{video_details.get('title')}' by '{video_details.get('channelTitle')}'", file=sys.stderr)
                    mismatched.append({
                        'track_info': track,
                        'video_id': video_id,
                        'youtube_title': video_details.get('title', ''),
                        'youtube_channel': video_details.get('channelTitle', '')
                    })
                    not_found.append(track)
            else:
                print(f"  Found video ID but couldn't get details: {video_id}", file=sys.stderr)
                not_found.append(track)
        else:
            print(f"  Not found: {track['artist']} - {track['title']}", file=sys.stderr)
            not_found.append(track)
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.1)
    
    # Add all found tracks to playlist in batch
    if track_search_results:
        video_ids = [result['video_id'] for result in track_search_results]
        print(f"Adding {len(video_ids)} tracks to playlist...", file=sys.stderr)
        
        try:
            responses, errors = add_tracks_to_playlist(youtube_service, playlist_id, video_ids)
            
            # Handle any errors during adding
            if errors:
                print(f"Encountered {len(errors)} errors while adding tracks:", file=sys.stderr)
                for video_id, error in errors:
                    # Find the track info for this video_id
                    track_info = next((result['track_info'] for result in track_search_results if result['video_id'] == video_id), None)
                    if track_info:
                        track_name = f"{track_info['artist']} - {track_info['title']}"
                    else:
                        track_name = f"Unknown track ({video_id})"
                    print(f"  Failed to add {track_name}: {error}", file=sys.stderr)
                    not_found.append(track_info if track_info else {'artist': '', 'title': f'Unknown ({video_id})'})
            
            print(f"Successfully added {len(responses)} tracks to playlist", file=sys.stderr)
        except Exception as e:
            print(f"Error adding tracks to playlist: {e}", file=sys.stderr)
            # If batch add fails, try adding individually
            print("Falling back to individual track adding...", file=sys.stderr)
            for result in track_search_results:
                try:
                    add_tracks_to_playlist(youtube_service, playlist_id, [result['video_id']])
                    print(f"  Added: {result['video_id']}", file=sys.stderr)
                except Exception as e:
                    print(f"  Failed to add {result['video_id']}: {e}", file=sys.stderr)
                    not_found.append(result['track_info'])
    
    # Add mismatched tracks to the not_found list and print details
    if mismatched:
        print(f"\nFound {len(mismatched)} tracks with potential mismatches:", file=sys.stderr)
        for item in mismatched:
            track = item['track_info']
            print(f"  Expected: {track['artist']} - {track['title']}", file=sys.stderr)
            print(f"  Found: {item['youtube_title']} by {item['youtube_channel']}", file=sys.stderr)
            print(f"  Video ID: {item['video_id']}", file=sys.stderr)
            print(file=sys.stderr)
    
    return not_found

def create_youtube_playlist_from_draft(title: str, draft_tracks: List[Dict[str, Any]], prefix: str = "") -> List[Dict[str, Any]]:
    """Create a YouTube playlist from draft tracks"""
    # Add prefix to title if specified
    if prefix:
        title = f"{prefix}: {title}"
    
    # Get YouTube credentials and service
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    # Create or find playlist
    playlist_id, was_created = create_or_find_playlist(youtube_service, title)
    if was_created:
        print(f"Created playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    else:
        print(f"Found existing playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    
    # Filter tracks marked for inclusion and have video IDs
    tracks_to_add = [track for track in draft_tracks if track.get('include', False) and track.get('video_id')]
    
    if not tracks_to_add:
        print("No tracks marked for inclusion", file=sys.stderr)
        return []
    
    # Add tracks to playlist
    video_ids = [track['video_id'] for track in tracks_to_add]
    print(f"Adding {len(video_ids)} tracks to playlist...", file=sys.stderr)
    
    try:
        responses, errors = add_tracks_to_playlist(youtube_service, playlist_id, video_ids)
        
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
        return draft_tracks

def save_draft(title: str, tracks: List[Dict[str, str]], program_id: str, filename: str) -> None:
    """Save playlist draft with search results to JSON file"""
    # Get YouTube credentials and service for searching
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    draft_tracks = []
    
    for i, track in enumerate(tracks, 1):
        search_query = f"{track['artist']} {track['title']}".strip()
        print(f"Searching for track {i}/{len(tracks)}: {search_query}", file=sys.stderr)
        
        video_id = search_track_with_cache(youtube_service, search_query)
        
        if video_id:
            # Get video details to assess match quality
            video_details = get_video_details(youtube_service, video_id)
            if video_details:
                yt_title = video_details.get('title', '')
                yt_channel = video_details.get('channelTitle', '')
                
                # Assess match quality
                expected_artist = track['artist'].lower()
                expected_title = track['title'].lower()
                
                artist_match = expected_artist in yt_title.lower() or expected_artist in yt_channel.lower()
                title_match = expected_title in yt_title.lower()
                
                if artist_match and title_match:
                    status = "exact_match"
                    include = True
                    notes = ""
                elif artist_match or title_match:
                    status = "suspect_match"
                    include = False
                    notes = "Partial match - please verify"
                else:
                    status = "suspect_match"
                    include = False
                    notes = "Poor match - please verify"
                
                draft_tracks.append({
                    "bbc_artist": track['artist'],
                    "bbc_title": track['title'],
                    "status": status,
                    "video_id": video_id,
                    "youtube_title": yt_title,
                    "youtube_channel": yt_channel,
                    "include": include,
                    "notes": notes
                })
            else:
                draft_tracks.append({
                    "bbc_artist": track['artist'],
                    "bbc_title": track['title'],
                    "status": "not_found",
                    "video_id": None,
                    "youtube_title": None,
                    "youtube_channel": None,
                    "include": False,
                    "notes": "Could not get video details"
                })
        else:
            draft_tracks.append({
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
    
    draft_data = {
        "playlist_title": title,
        "program_id": program_id,
        "tracks": draft_tracks,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(draft_data, f, indent=2, ensure_ascii=False)
    
    print(f"Draft saved to: {filename}", file=sys.stderr)

def load_draft(filename: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Load playlist draft from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            draft_data = json.load(f)
        
        # Handle both old and new draft formats
        if "playlist_title" in draft_data:
            # New format
            title = draft_data.get("playlist_title", "")
            tracks = draft_data.get("tracks", [])
        else:
            # Old format - convert to new format
            title = draft_data.get("title", "")
            old_tracks = draft_data.get("tracks", [])
            tracks = []
            for track in old_tracks:
                tracks.append({
                    "bbc_artist": track.get("artist", ""),
                    "bbc_title": track.get("title", ""),
                    "status": "unknown",
                    "video_id": None,
                    "youtube_title": None,
                    "youtube_channel": None,
                    "include": False,
                    "notes": "Old format - needs search"
                })
        
        return title, tracks
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
        # Handle old-style usage: program_id as positional argument
        if len(sys.argv) > 1:
            args.command = 'create'
            args.program_id = sys.argv[1]
            args.prefix = None
        else:
            parser.print_help()
            sys.exit(1)

    if args.command == 'draft':
        # Parse BBC playlist and save as draft
        print("Fetching BBC playlist...", file=sys.stderr)
        title, tracks = parse_bbc_playlist(args.program_id)

        if not title or not tracks:
            print("Failed to parse BBC playlist", file=sys.stderr)
            sys.exit(1)

        print(f"Found playlist: {title}", file=sys.stderr)
        print(f"Found {len(tracks)} tracks", file=sys.stderr)

        # Determine output filename
        output_file = args.output if args.output else f"{args.program_id}.json"
        save_draft(title, tracks, args.program_id, output_file)
        
        print(f"\nYou can now edit the draft file '{output_file}' to modify tracks before creating the playlist.", file=sys.stderr)
        print(f"To create the playlist, run: gp2ytm bbc create --draft {output_file}", file=sys.stderr)

    elif args.command in ['create', 'print']:
        # Load playlist data from either BBC or draft file
        if hasattr(args, 'program_id') and args.program_id:
            print("Fetching BBC playlist...", file=sys.stderr)
            title, tracks = parse_bbc_playlist(args.program_id)
            
            if not title or not tracks:
                print("Failed to parse BBC playlist", file=sys.stderr)
                sys.exit(1)

            print(f"Playlist: {title}", file=sys.stderr)
            print(f"Found {len(tracks)} tracks", file=sys.stderr)

            if args.command == 'print':
                # Just print the tracks without creating a YouTube playlist
                print("\nTracks in playlist:")
                for i, track in enumerate(tracks, 1):
                    print(f"{i}. {track['artist']} - {track['title']}")
            else:
                # Create YouTube playlist and add tracks (old workflow)
                print("Creating YouTube playlist...", file=sys.stderr)
                not_found = create_youtube_playlist(title, tracks, args.prefix if hasattr(args, 'prefix') else "")

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
            title, draft_tracks = load_draft(args.draft)
            
            if not title or not draft_tracks:
                print("Failed to load draft data", file=sys.stderr)
                sys.exit(1)

            print(f"Playlist: {title}", file=sys.stderr)
            print(f"Found {len(draft_tracks)} tracks", file=sys.stderr)

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
                not_included = create_youtube_playlist_from_draft(title, draft_tracks, args.prefix if hasattr(args, 'prefix') else "")

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
