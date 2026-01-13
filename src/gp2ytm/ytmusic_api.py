import os
import sys
import argparse
from typing import List, Tuple, Optional, Dict, Any
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Add YouTube Data API scope for playlist management
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'openid',
    'https://www.googleapis.com/auth/youtube'  # Add this for YouTube access
]

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

def create_playlist(youtube_service: Resource, title: str, description: str = "", privacy_status: str = "private") -> Dict[str, Any]:
    """Create a YouTube playlist"""
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
    return response

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
    """Search for a music track on YouTube Music"""
    # Try multiple search variations for better results
    search_variations = [
        query + " official audio",
        query + " music",
        query + " official music video"
    ]
    
    for search_query in search_variations:
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
                item = response['items'][0]
                # Filter for music-like content
                title = item['snippet']['title'].lower()
                if 'official' in title or 'audio' in title or 'lyric' in title:
                    return item['id']['videoId']
        except Exception as e:
            print(f"Search error for query '{search_query}': {e}", file=sys.stderr)
            continue
    
    # Fallback to first result if no perfect match
    try:
        request = youtube_service.search().list(
            part='snippet',
            q=query,
            type='video',
            videoCategoryId='10',  # Music category
            maxResults=1
        )
        response = request.execute()
        if response['items']:
            return response['items'][0]['id']['videoId']
    except Exception as e:
        print(f"Search error for query '{query}': {e}", file=sys.stderr)
    
    return None

def main() -> None:
    # TODO: add a subcommand to add a track ID to a playlist ID
    parser = argparse.ArgumentParser(description='YouTube Music API tools')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create playlist subcommand
    create_parser = subparsers.add_parser('create-playlist', help='Create a new YouTube playlist')
    create_parser.add_argument('name', help='Name of the playlist to create')
    
    # Search track subcommand
    search_parser = subparsers.add_parser('search-track', help='Search for a track and return its ID')
    search_parser.add_argument('query', help='Search query for the track')
    
    # Add track to playlist subcommand
    add_parser = subparsers.add_parser('add-track', help='Add a track to a playlist')
    add_parser.add_argument('playlist_id', help='ID of the playlist to add track to')
    add_parser.add_argument('video_id', help='ID of the video/track to add')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    creds = get_credentials()
    youtube_service: Resource = build('youtube', 'v3', credentials=creds)
    
    if args.command == 'create-playlist':
        playlist = create_playlist(youtube_service, args.name)
        print(f"Created playlist: {playlist['snippet']['title']}")
        print(f"Playlist ID: {playlist['id']}")
    
    elif args.command == 'search-track':
        video_id = search_track(youtube_service, args.query)
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

if __name__ == "__main__":
    main()
