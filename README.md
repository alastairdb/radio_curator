# Radio Curator - BBC Radio Show Downloader and Playlist Curator

This tool downloads BBC radio shows and curates their playlists. It can fetch track listings from BBC program pages, download radio shows using get_iplayer, and create corresponding playlists in your YouTube Music account.

## Features

- Downloads BBC radio shows using get_iplayer
- Fetches track listings from BBC radio program pages
- Adds playlist metadata to downloaded audio files
- Creates YouTube Music playlists with the same name as the BBC program
- Automatically searches for tracks on YouTube Music
- Handles authentication with Google/YouTube Music
- Integrates with Jellyfin media server
- Reports any tracks that couldn't be found
- Can print tracks without creating a playlist

## Prerequisites

1. Python 3.13 or higher
2. Google account with YouTube Music access

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -e .
   ```
   
   For development:
   ```bash
   pip install -e ".[dev,test]"
   ```

3. Set up YouTube Music authentication:
   ```bash
   radio_curator ytmusic-api setup
   ```
   
   This will guide you through copying your browser's authentication headers. Follow these steps:
   - Open YouTube Music (https://music.youtube.com) in your browser and log in
   - Open Developer Tools (F12 or Ctrl+Shift+I)
   - Go to the Network tab
   - Filter by `/browse` in the search bar
   - Scroll down or click Library to trigger a request
   - Find a POST request to `browse?...` with status 200
   - Right-click and copy the request headers
   - Paste them when prompted by the setup command

## Usage

### Download Radio Shows

```bash
# Download a BBC radio show
radio_curator download <program_id>

# Download with Jellyfin integration (set environment variables first)
export JELLYFIN_LIBRARY_DIR="/path/to/jellyfin/music"
export JELLYFIN_URL="http://localhost:8096"
export JELLYFIN_API_TOKEN="your_api_token"
radio_curator download <program_id>
```

### BBC Playlist Commands

```bash
# Parse BBC playlist and save as draft file for editing
radio_curator bbc draft <program_id> [--output FILENAME]

# Create a YouTube Music playlist from a BBC program
radio_curator bbc create --program-id <program_id> [--prefix PREFIX]

# Create a YouTube Music playlist from a draft file
radio_curator bbc create --draft <draft_file> [--prefix PREFIX]

# Just print the tracks without creating a playlist
radio_curator bbc print --program-id <program_id>
radio_curator bbc print --draft <draft_file>
```

Examples:
```bash
# Download a radio show
radio_curator download m0012345

# Two-stage workflow (recommended)
radio_curator bbc draft m0012345
# Edit m0012345.json as needed
radio_curator bbc create --draft m0012345.json

# Direct creation (old workflow)
radio_curator bbc create --program-id m0012345

# Print tracks from BBC or draft
radio_curator bbc print --program-id m0012345
radio_curator bbc print --draft m0012345.json
```

The program ID can be found in the URL of any BBC radio program page. For example, in `https://www.bbc.co.uk/programmes/m0012345`, the program ID is `m0012345`.

### YouTube Music API Tools

```bash
radio_curator ytmusic-api <command> [arguments]
```

Available commands:
- `setup` - Set up browser authentication (run this first)
- `create-playlist <title> [description] [privacy]` - Create a new playlist
- `search-track <query>` - Search for a track and return its video ID
- `add-track <playlist_id> <video_id>` - Add a track to a playlist
- `print-tracks <query>` - Print tracks without creating a playlist

Examples:
```bash
radio_curator ytmusic-api setup
radio_curator ytmusic-api create-playlist "My Playlist" "Description" "PRIVATE"
radio_curator ytmusic-api search-track "Artist - Song Title"
radio_curator ytmusic-api add-track "playlist_id" "video_id"
radio_curator ytmusic-api print-tracks "Artist1 - Song1, Artist2 - Song2"
```

## First Run

On first run, you'll need to authenticate with YouTube Music using browser headers:
1. Run `radio_curator ytmusic-api setup` to start the authentication process
2. Follow the prompts to copy your browser's request headers from YouTube Music
3. The tool will save the authentication headers for future use (valid for ~2 years)

The browser authentication method doesn't require Google Cloud Platform setup and has no rate limits.

## How It Works

### Two-Stage Workflow (Recommended)
1. **Create Draft**: Parse the BBC program page and save track information to a JSON file
2. **Edit Draft**: Manually review and edit the track list (fix artist names, remove unwanted tracks, etc.)
3. **Create Playlist**: Generate the YouTube Music playlist from the edited draft file

### Direct Workflow
1. **Fetch BBC Playlist**: The tool scrapes the BBC program page to extract artist and track information
2. **Create YouTube Playlist**: A new playlist is created in your YouTube Music account
3. **Search Tracks**: Each track is searched on YouTube Music using various search strategies
4. **Add to Playlist**: Found tracks are added to the new playlist
5. **Report Results**: Any tracks that couldn't be found are reported

### Draft File Format

The draft file is a JSON file containing metadata about the playlist and a list of tracks. Here is a detailed description of each field:

```json
{
  "playlist_title": "Gary Bartz in conversation",
  "program_id": "m002pr92",
  "broadcast_date": "2025-12-27",
  "description": "Gilles delves deep into his record collection...",
  "tracks": [
    {
      "bbc_artist": "T2",
      "bbc_title": "J.L.T",
      "status": "exact_match",
      "video_id": "s2mh23x1c7M",
      "youtube_title": "J.L.T.",
      "youtube_channel": "T2",
      "include": true,
      "notes": ""
    },
    {
      "bbc_artist": "The Green Wings",
      "bbc_title": "Vrati Se Lađo Moja",
      "status": "suspect_match",
      "video_id": "ccLJD0037_A",
      "youtube_title": "The Green Wings - Vrati Se Lađo Moja",
      "youtube_channel": "kohncke",
      "include": false,
      "notes": "Partial match - please verify"
    }
  ],
  "created_at": "2026-01-19 13:58:06"
}
```

#### Top-Level Fields
- **playlist_title**: The title of the playlist, extracted from the BBC program page.
- **program_id**: The unique identifier for the BBC program (e.g., `m002pr92`).
- **broadcast_date**: The date the program was broadcast, in `YYYY-MM-DD` format.
- **description**: A description of the program, extracted from the BBC page.
- **created_at**: The timestamp when the draft file was generated.
- **tracks**: A list of track objects, each representing a song played in the program.

#### Track Object Fields
- **bbc_artist**: The artist name as listed on the BBC program page.
- **bbc_title**: The track title as listed on the BBC program page.
- **status**: The result of the automated search. Possible values:
  - `exact_match`: High confidence match found.
  - `suspect_match`: A potential match was found but confidence is low (e.g., artist mismatch).
  - `not_found`: No suitable match was found on YouTube Music.
- **video_id**: The YouTube video ID of the found track (or `null` if not found).
- **youtube_title**: The title of the track found on YouTube Music.
- **youtube_channel**: The artist or channel name associated with the YouTube track.
- **include**: A boolean flag (`true` or `false`) indicating whether this track should be added to the final playlist.
  - Defaults to `true` for `exact_match`.
  - Defaults to `false` for `suspect_match` or `not_found`.
  - **You should manually change this to `true` for any suspect matches you verify are correct.**
- **notes**: Additional information about the match status (e.g., "Partial match - please verify").


#### Nota Bene

Currently, the YouTube Music web interface offers a "Stats for nerds" option for the
currently playing track. This will give you the **video_id** that you can add to the draft
file by hand.

The repo contains the file `ytm-draft-helper.el` which makes editing the draft file easier
for Emacs users.

## Limitations

- Some tracks may not be found if they're not available on YouTube Music
- BBC program pages must have a "Music Played" section
- Rate limits may apply to YouTube API usage
