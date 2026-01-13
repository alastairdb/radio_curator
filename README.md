# GP2YTM - BBC Radio Playlist to YouTube Music Converter

This tool (semi-)automatically converts BBC radio program playlists to YouTube Music playlists. It fetches the track listing from a BBC program page and creates a corresponding playlist in your YouTube Music account.

## Features

- Fetches track listings from BBC radio program pages
- Creates YouTube Music playlists with the same name as the BBC program
- Automatically searches for tracks on YouTube Music
- Handles authentication with Google/YouTube Music
- Reports any tracks that couldn't be found

## Prerequisites

1. Python 3.13 or higher
2. Google account with YouTube Music access
3. Google Cloud Platform project with YouTube Data API enabled
4. OAuth 2.0 credentials file (`credentials.json`) from Google Cloud Platform

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -e .
   ```

3. Set up Google API credentials:
   - Create a Google Cloud Platform project
   - Enable the YouTube Data API v3
   - Create OAuth 2.0 credentials
   - Download the credentials file as `credentials.json` in the project directory

## Usage

### Convert BBC Playlist to YouTube Music

```bash
gp2ytm bbc-playlist <program_id>
```

Example:
```bash
gp2ytm bbc-playlist m0012345
```

The program ID can be found in the URL of any BBC radio program page. For example, in `https://www.bbc.co.uk/programmes/m0012345`, the program ID is `m0012345`.

### YouTube Music API Tools

```bash
gp2ytm ytmusic-api <command> [arguments]
```

Available commands:
- `create-playlist <title> [description] [privacy]` - Create a new playlist
- `search-track <query>` - Search for a track and return its video ID
- `add-tracks <playlist_id> <video_id> [video_id ...]` - Add tracks to a playlist

Examples:
```bash
gp2ytm ytmusic-api create-playlist "My Playlist" "Description" "private"
gp2ytm ytmusic-api search-track "Artist - Song Title"
gp2ytm ytmusic-api add-tracks "playlist_id" "video_id1" "video_id2"
```

## First Run

On first run, you'll need to authenticate with Google:
1. The tool will open a browser window
2. Sign in to your Google account
3. Grant permission to manage your YouTube account
4. The tool will save an authentication token for future use

## How It Works

1. **Fetch BBC Playlist**: The tool scrapes the BBC program page to extract artist and track information
2. **Create YouTube Playlist**: A new playlist is created in your YouTube Music account
3. **Search Tracks**: Each track is searched on YouTube Music using various search strategies
4. **Add to Playlist**: Found tracks are added to the new playlist
5. **Report Results**: Any tracks that couldn't be found are reported

## Limitations

- Some tracks may not be found if they're not available on YouTube Music
- BBC program pages must have a "Music Played" section
- Rate limits may apply to YouTube API usage
