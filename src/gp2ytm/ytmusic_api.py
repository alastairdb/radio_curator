import os
import sys
import argparse
import json
from typing import List, Tuple, Optional, Dict, Any
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pathlib

# Add YouTube Data API scope for playlist management
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'openid',
    'https://www.googleapis.com/auth/youtube'  # Add this for YouTube access
]

# Simple in-memory cache for search results
_search_cache: Dict[str, str] = {}
# File to persist cache between runs in a proper cache directory
XDG_CACHE_HOME = os.environ.get('XDG_CACHE_HOME', os.path.join(pathlib.Path.home(), '.cache'))
CACHE_DIR = os.path.join(XDG_CACHE_HOME, 'gp2ytm')
CACHE_FILE = os.path.join(CACHE_DIR, 'search_cache.json')

def load_cache() -> None:
    """Load search cache from file"""
    global _search_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                _search_cache = json.load(f)
        except Exception:
            _search_cache = {}

def save_cache() -> None:
    """Save search cache to file"""
    try:
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(_search_cache, f)
    except Exception:
        pass

def get_credentials() -> Credentials:
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def find_playlist(youtube_service: Resource, title: str) -> Optional[str]:
    """Check if a playlist with the given title already exists"""
    try:
        request = youtube_service.playlists().list(
            part='snippet',
            mine=True,
            maxResults=50
        )
        response = request.execute()
        
        for item in response.get('items', []):
            if item['snippet']['title'] == title:
                return item['id']
    except Exception as e:
        print(f"Error checking for existing playlist: {e}", file=sys.stderr)
    
    return None

def create_or_find_playlist(youtube_service: Resource, title: str, description: str = "", privacy_status: str = "private") -> Tuple[str, bool]:
    """Create a new playlist or return existing one. Returns (playlist_id, was_created)"""
    existing_id = find_playlist(youtube_service, title)
    if existing_id:
        return existing_id, False
    
    playlist_body = {
        'snippet': {
            'title': title,
            'description': description
        },
        'status': {
            'privacyStatus': privacy_status
        }
    }
    
    request = youtube_service.playlists().insert(
        part='snippet,status',
        body=playlist_body
    )
    response = request.execute()
    return response['id'], True

def add_tracks_to_playlist(youtube_service: Resource, playlist_id: str, video_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Add multiple tracks to a YouTube playlist in batch"""
    responses: List[Dict[str, Any]] = []
    errors: List[Tuple[str, str]] = []
    
    for video_id in video_ids:
        try:
            request_body = {
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': video_id
                    }
                }
            }
            
            request = youtube_service.playlistItems().insert(
                part='snippet',
                body=request_body
            )
            response = request.execute()
            responses.append(response)
        except Exception as e:
            errors.append((video_id, str(e)))
    
    return responses, errors

def search_track(youtube_service: Resource, query: str) -> Optional[str]:
    """Search for a music track on YouTube Music with optimized search"""
    # Try just the most effective search variation
    search_query = query + " official audio"
    
    try:
        request = youtube_service.search().list(
            part='snippet',
            q=search_query,
            type='video',
            videoCategoryId='10',  # Music category
            maxResults=1
        )
        response = request.execute()
        
        if response['items']:
            return response['items'][0]['id']['videoId']
    except Exception as e:
        print(f"Search error for query '{search_query}': {e}", file=sys.stderr)
    
    return None

def get_video_details(youtube_service: Resource, video_id: str) -> Optional[Dict[str, Any]]:
    """Get details of a YouTube video by its ID"""
    try:
        request = youtube_service.videos().list(
            part='snippet',
            id=video_id
        )
        response = request.execute()
        
        if response['items']:
            return response['items'][0]['snippet']
        return None
    except Exception as e:
        print(f"Error getting video details for {video_id}: {e}", file=sys.stderr)
        return None

def search_track_with_cache(youtube_service: Resource, query: str) -> Optional[str]:
    """Search for a track with caching"""
    # Load cache if not already loaded
    if not _search_cache:
        load_cache()
    
    if query in _search_cache:
        return _search_cache[query]
    
    result = search_track(youtube_service, query)
    if result:
        _search_cache[query] = result
        save_cache()
    return result

def main() -> None:
    # TODO: add a subcommand to add a track ID to a playlist ID
    parser = argparse.ArgumentParser(description='YouTube Music API tools')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create playlist subcommand
    create_parser = subparsers.add_parser('create-playlist', help='Create a new YouTube playlist')
    create_parser.add_argument('name', help='Name of the playlist to create')
    create_parser.add_argument('description', nargs='?', default='', help='Description of the playlist')
    create_parser.add_argument('privacy', nargs='?', default='private', choices=['public', 'private', 'unlisted'], help='Privacy status of the playlist')
    
    # Search track subcommand
    search_parser = subparsers.add_parser('search-track', help='Search for a track and return its ID')
    search_parser.add_argument('query', help='Search query for the track')
    
    # Add track to playlist subcommand
    add_parser = subparsers.add_parser('add-track', help='Add a track to a playlist')
    add_parser.add_argument('playlist_id', help='ID of the playlist to add track to')
    add_parser.add_argument('video_id', help='ID of the video/track to add')
    
    # Print tracks subcommand (without creating a playlist)
    print_parser = subparsers.add_parser('print-tracks', help='Print tracks without creating a playlist')
    print_parser.add_argument('query', help='Search query for tracks (comma-separated)')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    if args.command == 'create-playlist':
        playlist_id, was_created = create_or_find_playlist(youtube_service, args.name, args.description, args.privacy)
        if was_created:
            print(f"Created playlist: {args.name}")
        else:
            print(f"Found existing playlist: {args.name}")
        print(f"Playlist ID: {playlist_id}")
    
    elif args.command == 'search-track':
        video_id = search_track_with_cache(youtube_service, args.query)
        if video_id:
            print(f"Found track ID: {video_id}")
        else:
            print("No track found for the given query")
    
    # Add track to playlist subcommand
    elif args.command == 'add-track':
        responses, errors = add_tracks_to_playlist(youtube_service, args.playlist_id, [args.video_id])
        if errors:
            print(f"Error adding track {args.video_id} to playlist {args.playlist_id}: {errors[0][1]}")
        else:
            print(f"Added track {args.video_id} to playlist {args.playlist_id}")
            print(f"Playlist item ID: {responses[0]['id']}")
    
    elif args.command == 'print-tracks':
        # Split the query string by commas and search for each track
        queries = [q.strip() for q in args.query.split(',')]
        print(f"Searching for {len(queries)} tracks...")
        
        for i, query in enumerate(queries, 1):
            print(f"\nTrack {i}/{len(queries)}: {query}")
            video_id = search_track_with_cache(youtube_service, query)
            
            if video_id:
                print(f"Found: {query}")
                print(f"Video ID: {video_id}")
                print(f"YouTube URL: https://www.youtube.com/watch?v={video_id}")
            else:
                print(f"Not found: {query}")

if __name__ == "__main__":
    main()
