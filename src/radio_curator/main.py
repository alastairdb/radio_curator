"""Main entry point for the RADIO_CURATOR application."""

import sys
import subprocess
import requests
import os
import glob
import shutil
import argparse
from mutagen.id3 import ID3, USLT
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen import File

from .ytmusic_api import main as ytmusic_api_main
from .bbc_playlist_to_ytmusic import main as bbc_playlist_main, parse_bbc_playlist
from radio_curator import __version__

def check_ip_location():
    """Check if the current IP address is in GB."""
    try:
        response = requests.get("https://ipinfo.io/json", timeout=10)
        response.raise_for_status()
        data = response.json()
        country = data.get("country", "")
        return country == "GB", country
    except Exception as e:
        print(f"Warning: Could not check IP location: {e}")
        return None, None

def format_playlist_for_lyrics(title, tracks, broadcast_date):
    """Format BBC playlist data for inclusion in lyrics tag."""
    lines = [f"BBC Playlist: {title}"]
    if broadcast_date:
        lines.append(f"Broadcast Date: {broadcast_date}")
    lines.append("")
    
    for i, track in enumerate(tracks, 1):
        artist = track.get('artist', 'Unknown Artist')
        song_title = track.get('title', 'Unknown Title')
        lines.append(f"{i:2d}. {artist} - {song_title}")
    
    return "\n".join(lines)

def add_playlist_to_audio_metadata(file_path, playlist_text):
    """Add playlist information to the lyrics tag of an audio file."""
    try:
        audio_file = File(file_path)
        if audio_file is None:
            print(f"Could not read audio file: {file_path}")
            return False
        
        if isinstance(audio_file, ID3):
            # MP3 file
            existing_lyrics = ""
            if 'USLT::eng' in audio_file:
                existing_lyrics = audio_file['USLT::eng'].text
            
            new_lyrics = existing_lyrics
            if existing_lyrics:
                new_lyrics += "\n\n" + playlist_text
            else:
                new_lyrics = playlist_text
            
            audio_file['USLT::eng'] = USLT(encoding=3, lang='eng', desc='', text=new_lyrics)
            audio_file.save()
            
        elif isinstance(audio_file, MP4):
            # M4A file
            existing_lyrics = audio_file.get('\xa9lyr', [''])[0]
            
            new_lyrics = existing_lyrics
            if existing_lyrics:
                new_lyrics += "\n\n" + playlist_text
            else:
                new_lyrics = playlist_text
            
            audio_file['\xa9lyr'] = [new_lyrics]
            audio_file.save()
            
        elif isinstance(audio_file, FLAC):
            # FLAC file
            existing_lyrics = audio_file.get('LYRICS', [''])[0]
            
            new_lyrics = existing_lyrics
            if existing_lyrics:
                new_lyrics += "\n\n" + playlist_text
            else:
                new_lyrics = playlist_text
            
            audio_file['LYRICS'] = [new_lyrics]
            audio_file.save()
            
        else:
            print(f"Unsupported audio format for file: {file_path}")
            return False
        
        print(f"Added playlist to lyrics tag of: {os.path.basename(file_path)}")
        return True
        
    except Exception as e:
        print(f"Error updating metadata for {file_path}: {e}")
        return False

def find_downloaded_audio_files(program_id, search_dir="."):
    """Find audio files that were likely downloaded by get_iplayer for the given program ID."""
    # get_iplayer typically downloads to current directory with program ID in filename
    patterns = [
        f"*{program_id}*.mp3",
        f"*{program_id}*.m4a", 
        f"*{program_id}*.flac",
        f"*{program_id}*.wav"
    ]
    
    found_files = []
    for pattern in patterns:
        full_pattern = os.path.join(search_dir, pattern)
        found_files.extend(glob.glob(full_pattern))
    
    return found_files

def move_files_to_jellyfin(audio_files, jellyfin_dir):
    """Move downloaded audio files to Jellyfin library directory."""
    moved_files = []
    
    if not os.path.exists(jellyfin_dir):
        print(f"Creating Jellyfin directory: {jellyfin_dir}")
        os.makedirs(jellyfin_dir, exist_ok=True)
    
    for file_path in audio_files:
        filename = os.path.basename(file_path)
        dest_path = os.path.join(jellyfin_dir, filename)
        
        try:
            shutil.move(file_path, dest_path)
            print(f"Moved {filename} to {jellyfin_dir}")
            moved_files.append(dest_path)
        except Exception as e:
            print(f"Error moving {filename}: {e}")
    
    return moved_files

def trigger_jellyfin_rescan(jellyfin_url, api_token, library_id=None):
    """Trigger a Jellyfin library rescan."""
    try:
        headers = {"X-Emby-Token": api_token}
        
        if library_id:
            url = f"{jellyfin_url}/Items/{library_id}/Refresh?Recursive=true"
        else:
            url = f"{jellyfin_url}/Library/Refresh"
        
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()
        print("Jellyfin library rescan triggered successfully")
        
    except Exception as e:
        print(f"Warning: Could not trigger Jellyfin rescan: {e}")

def download_radio_show(program_id, jellyfin_dir=None, jellyfin_url=None, jellyfin_token=None, jellyfin_library_id=None):
    """Download a radio show using get_iplayer."""
    # Check IP location first
    is_gb, country = check_ip_location()
    
    if is_gb is False:
        print(f"Warning: Your IP address appears to be in {country}, not GB.")
        print("BBC iPlayer content may not be available outside the UK.")
        response = input("Do you want to continue anyway? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("Download cancelled.")
            return
    elif is_gb is None:
        print("Could not verify IP location. Proceeding with download...")
    else:
        print("IP location verified: GB")
    
    try:
        cmd = ["get_iplayer", "--force", f"--pid={program_id}", "--type=radio"]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True)
        print(f"Successfully downloaded radio show with PID: {program_id}")
        
        # Try to get BBC playlist and add to audio metadata
        try:
            print("Fetching BBC playlist data...")
            title, tracks, broadcast_date, _ = parse_bbc_playlist(program_id)
            if tracks:
                playlist_text = format_playlist_for_lyrics(title, tracks, broadcast_date)
                
                # Find downloaded audio files
                audio_files = find_downloaded_audio_files(program_id)
                
                if audio_files:
                    print(f"Found {len(audio_files)} audio file(s), adding playlist to metadata...")
                    for audio_file in audio_files:
                        add_playlist_to_audio_metadata(audio_file, playlist_text)
                    
                    # Move files to Jellyfin library if specified
                    if jellyfin_dir:
                        moved_files = move_files_to_jellyfin(audio_files, jellyfin_dir)
                        
                        # Trigger Jellyfin rescan if configured
                        if jellyfin_url and jellyfin_token and moved_files:
                            print("Triggering Jellyfin library rescan...")
                            trigger_jellyfin_rescan(jellyfin_url, jellyfin_token, jellyfin_library_id)
                else:
                    print("No audio files found to update with playlist data")
            else:
                print("No playlist tracks found for this program")
                
        except Exception as e:
            print(f"Warning: Could not add playlist to audio metadata: {e}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error downloading radio show: {e}")
        if e.stdout:
            print("Output:", e.stdout)
        if e.stderr:
            print("Error output:", e.stderr)
    except FileNotFoundError:
        print("Error: get_iplayer not found. Please install get_iplayer first.")

def main():
    """Main entry point."""
    # Use argparse for better argument handling including --version
    parser = argparse.ArgumentParser(
        description="BBC radio show downloader and playlist curator",
        prog="radio_curator"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # ytmusic-api command
    subparsers.add_parser("ytmusic-api", help="YouTube Music API utilities")
    
    # bbc command
    subparsers.add_parser("bbc", help="BBC playlist utilities")
    
    # bbc-playlist command (backward compatibility)
    subparsers.add_parser("bbc-playlist", help="BBC playlist utilities (deprecated, use 'bbc')")
    
    # download command
    download_parser = subparsers.add_parser("download", help="Download radio shows")
    download_parser.add_argument("program_id", help="BBC program ID (e.g., b006wkqb)")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    if args.command == "ytmusic-api":
        # Remove the command from argv and pass the rest to the module
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        ytmusic_api_main()
    elif args.command == "bbc":
        # Remove the command from argv and pass the rest to the module
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        bbc_playlist_main()
    elif args.command == "bbc-playlist":
        # Keep backward compatibility
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        bbc_playlist_main()
    elif args.command == "download":
        if args.program_id in ["--help", "-h"]:
            download_parser.print_help()
            return
        
        # Get Jellyfin configuration from environment variables
        jellyfin_dir = os.environ.get('JELLYFIN_LIBRARY_DIR')
        jellyfin_url = os.environ.get('JELLYFIN_URL')
        jellyfin_token = os.environ.get('JELLYFIN_API_TOKEN')
        jellyfin_library_id = os.environ.get('JELLYFIN_LIBRARY_ID')
        
        download_radio_show(args.program_id, jellyfin_dir, jellyfin_url, jellyfin_token, jellyfin_library_id)
    else:
        print(f"Unknown command: {args.command}")
        print("Available commands: ytmusic-api, bbc, download")

if __name__ == "__main__":
    main()
