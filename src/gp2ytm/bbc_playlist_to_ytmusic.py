import json
import os
import re
import sys
import time
from typing import List, Dict, Tuple, Any
from googleapiclient.discovery import Resource

import requests
from bs4 import BeautifulSoup

# Import the YouTube API functions from the same package
from .ytmusic_api import get_credentials, build, search_track, create_playlist, add_tracks_to_playlist


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
    if skip_links:
        skip_links.decompose()

    # Extract title from the h1 tag
    title_element = soup.find("h1")
    title = (
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

        if segments_list:
            # Look for track entries within the segments-list
            track_elements = segments_list.find_all(["li", "div"], recursive=False)

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
        if segments_list:
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

    return title, tracks

def create_youtube_playlist(title: str, tracks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Create a YouTube playlist from BBC tracks"""
    # Get YouTube credentials and service
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    # Create playlist
    playlist = create_playlist(youtube_service, title)
    playlist_id = playlist['id']
    print(f"Created playlist: {title} (ID: {playlist_id})", file=sys.stderr)
    
    # Search for all tracks first
    track_search_results: List[Dict[str, Any]] = []
    not_found: List[Dict[str, str]] = []
    
    for i, track in enumerate(tracks, 1):
        search_query = f"{track['artist']} {track['title']}".strip()
        print(f"Searching for track {i}/{len(tracks)}: {search_query}", file=sys.stderr)
        
        video_id = search_track(youtube_service, search_query)
        if video_id:
            track_search_results.append({
                'track_info': track,
                'video_id': video_id,
                'search_query': search_query
            })
            print(f"  Found: {video_id}", file=sys.stderr)
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
    
    return not_found

def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python bbc_playlist_to_ytmusic.py <bbc_program_id>", file=sys.stderr
        )
        sys.exit(1)

    program_id = sys.argv[1]

    # Parse BBC playlist
    print("Fetching BBC playlist...", file=sys.stderr)
    title, tracks = parse_bbc_playlist(program_id)

    if not title or not tracks:
        print("Failed to parse BBC playlist", file=sys.stderr)
        sys.exit(1)

    print(f"Found playlist: {title}", file=sys.stderr)
    print(f"Found {len(tracks)} tracks", file=sys.stderr)

    # Create YouTube playlist and add tracks
    print("Creating YouTube playlist...", file=sys.stderr)
    not_found = create_youtube_playlist(title, tracks)

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


if __name__ == "__main__":
    main()
