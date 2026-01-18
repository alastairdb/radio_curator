# GP2YTM - BBC Radio Playlist to YouTube Music Converter

This tool (semi-)automatically converts BBC radio program playlists to YouTube Music playlists. It fetches the track listing from a BBC program page and creates a corresponding playlist in your YouTube Music account.

## Features

- Fetches track listings from BBC radio program pages
- Creates YouTube Music playlists with the same name as the BBC program
- Automatically searches for tracks on YouTube Music
- Handles authentication with Google/YouTube Music
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
   gp2ytm ytmusic-api setup
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

### BBC Playlist Commands

```bash
# Parse BBC playlist and save as draft file for editing
gp2ytm bbc draft <program_id> [--output FILENAME]

# Create a YouTube Music playlist from a BBC program
gp2ytm bbc create --program-id <program_id> [--prefix PREFIX]

# Create a YouTube Music playlist from a draft file
gp2ytm bbc create --draft <draft_file> [--prefix PREFIX]

# Just print the tracks without creating a playlist
gp2ytm bbc print --program-id <program_id>
gp2ytm bbc print --draft <draft_file>
```

Examples:
```bash
# Two-stage workflow (recommended)
gp2ytm bbc draft m0012345
# Edit m0012345.json as needed
gp2ytm bbc create --draft m0012345.json

# Direct creation (old workflow)
gp2ytm bbc create --program-id m0012345

# Print tracks from BBC or draft
gp2ytm bbc print --program-id m0012345
gp2ytm bbc print --draft m0012345.json
```

The program ID can be found in the URL of any BBC radio program page. For example, in `https://www.bbc.co.uk/programmes/m0012345`, the program ID is `m0012345`.

### YouTube Music API Tools

```bash
gp2ytm ytmusic-api <command> [arguments]
```

Available commands:
- `setup` - Set up browser authentication (run this first)
- `create-playlist <title> [description] [privacy]` - Create a new playlist
- `search-track <query>` - Search for a track and return its video ID
- `add-track <playlist_id> <video_id>` - Add a track to a playlist
- `print-tracks <query>` - Print tracks without creating a playlist

Examples:
```bash
gp2ytm ytmusic-api setup
gp2ytm ytmusic-api create-playlist "My Playlist" "Description" "PRIVATE"
gp2ytm ytmusic-api search-track "Artist - Song Title"
gp2ytm ytmusic-api add-track "playlist_id" "video_id"
gp2ytm ytmusic-api print-tracks "Artist1 - Song1, Artist2 - Song2"
```

## First Run

On first run, you'll need to authenticate with YouTube Music using browser headers:
1. Run `gp2ytm ytmusic-api setup` to start the authentication process
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
The draft file is a JSON file with the following structure:
```json
{
  "title": "BBC Program Title",
  "tracks": [
    {
      "artist": "Artist Name",
      "title": "Track Title"
    }
  ],
  "created_at": "2024-01-01 12:00:00"
}
```

## Limitations

- Some tracks may not be found if they're not available on YouTube Music
- BBC program pages must have a "Music Played" section
- Rate limits may apply to YouTube API usage
