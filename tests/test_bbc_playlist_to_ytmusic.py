"""Tests for BBC playlist to YouTube Music conversion."""

import pytest
from unittest.mock import patch, Mock, mock_open, MagicMock
import sys
import json
import tempfile
import os
from io import StringIO
from src.gp2ytm.bbc_playlist_to_ytmusic import (
    parse_bbc_playlist, create_youtube_playlist, create_youtube_playlist_from_draft,
    save_draft, load_draft, main
)

@pytest.fixture
def mock_bbc_html():
    """Sample BBC HTML content for testing."""
    return """
    <html>
    <head><title>Test BBC Programme</title></head>
    <body>
        <div class="orb-skip-links">Skip navigation</div>
        <h1>Test BBC Programme Title</h1>
        <span class="broadcast-event__date">Sat 27 Dec 2025</span>
        <div class="synopsis-toggle__long">
            <p>This is a test programme description.</p>
            <p>It has multiple paragraphs.</p>
        </div>
        <h2>Music Played</h2>
        <div class="segments-list">
            <li class="segments-list__item--music">
                <div class="segment__track">
                    <h3>Track Title</h3>
                    <span class="artist">Artist One</span>
                    <p class="no-margin"><span>Track One</span></p>
                </div>
            </li>
            <li class="segments-list__item--music">
                <div class="segment__track">
                    <h3>Track Title</h3>
                    <span class="artist">Artist Two</span>
                    <p class="no-margin"><span>Track Two</span></p>
                </div>
            </li>
            <li class="segments-list__item--music">
                <div class="segment__track">
                    <h3>Track Title</h3>
                    <span class="artist">Live Artist</span>
                    <p class="no-margin"><span>Live at Maida Vale Session</span></p>
                </div>
            </li>
        </div>
    </body>
    </html>
    """

@pytest.fixture
def mock_bbc_html_minimal():
    """Minimal BBC HTML content for testing edge cases."""
    return """
    <html>
    <body>
        <h1>Minimal Programme</h1>
        <h2>Music Played</h2>
        <div class="segments-list">
            <li class="segments-list__item--music">
                <div class="segment__track">
                    <h3 class="gamma no-margin">
                        <span class="artist">Solo Artist</span>
                   </h3>
                    <p class="no-margin"><span>Solo Track</span></p>
                </div>
            </li>
        </div>
    </body>
    </html>
    """

@pytest.fixture
def mock_bbc_html_no_music():
    """BBC HTML content with no music section."""
    return """
    <html>
    <body>
        <h1>No Music Programme</h1>
        <h2>Programme Content</h2>
        <div>No music played</div>
    </body>
    </html>
    """

@pytest.fixture
def mock_ytmusic():
    """Create a mock YTMusic instance."""
    mock = Mock()
    mock.get_library_playlists.return_value = []
    mock.create_playlist.return_value = 'test_playlist_id'
    mock.add_playlist_items.return_value = {'status': 'success'}
    mock.search.return_value = [
        {
            'videoId': 'test_video_id',
            'title': 'Test Track',
            'artists': [{'name': 'Test Artist'}]
        }
    ]
    return mock

@pytest.fixture
def sample_tracks():
    """Sample track data for testing."""
    return [
        {"artist": "Artist One", "title": "Track One"},
        {"artist": "Artist Two", "title": "Track Two"},
        {"artist": "D'Angelo", "title": "Feel Like Makin' Love"}
    ]

@pytest.fixture
def sample_draft_tracks():
    """Sample draft track data for testing."""
    return [
        {
            "bbc_artist": "Artist One",
            "bbc_title": "Track One",
            "status": "exact_match",
            "video_id": "video_id_1",
            "youtube_title": "Track One",
            "youtube_channel": "Artist One",
            "include": True,
            "notes": ""
        },
        {
            "bbc_artist": "Artist Two",
            "bbc_title": "Track Two",
            "status": "suspect_match",
            "video_id": "video_id_2",
            "youtube_title": "Track Two (Remix)",
            "youtube_channel": "Artist Two",
            "include": False,
            "notes": "Partial match - please verify"
        },
        {
            "bbc_artist": "Unknown Artist",
            "bbc_title": "Unknown Track",
            "status": "not_found",
            "video_id": None,
            "youtube_title": None,
            "youtube_channel": None,
            "include": False,
            "notes": "Could not find on YouTube"
        }
    ]

@pytest.fixture
def sample_draft_data(sample_draft_tracks):
    """Sample draft file data for testing."""
    return {
        "playlist_title": "Test Draft Playlist",
        "program_id": "test_program",
        "broadcast_date": "2025-12-27",
        "description": "Test description",
        "tracks": sample_draft_tracks,
        "created_at": "2025-01-01 12:00:00"
    }

class TestParseBbcPlaylist:
    """Tests for parse_bbc_playlist function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_success(self, mock_get, mock_bbc_html):
        """Test successful BBC playlist parsing."""
        mock_response = Mock()
        mock_response.text = mock_bbc_html
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        title, tracks, broadcast_date, description = parse_bbc_playlist("test_program_id")
        
        assert title == "Test BBC Programme Title"
        assert len(tracks) == 2  # Should exclude "Live at Maida Vale" track
        assert tracks[0] == {"artist": "Artist One", "title": "Track One"}
        assert tracks[1] == {"artist": "Artist Two", "title": "Track Two"}
        assert broadcast_date == "2025-12-27"
        assert "This is a test programme description." in description
        assert "It has multiple paragraphs." in description

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_minimal(self, mock_get, mock_bbc_html_minimal):
        """Test BBC playlist parsing with minimal content."""
        mock_response = Mock()
        mock_response.text = mock_bbc_html_minimal
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        title, tracks, broadcast_date, description = parse_bbc_playlist("test_program_id")
        
        assert title == "Minimal Programme"
        assert len(tracks) == 1
        assert tracks[0] == {"artist": "Solo Artist", "title": "Solo Track"}
        assert broadcast_date == ""
        assert description == ""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_no_music_section(self, mock_get, mock_bbc_html_no_music):
        """Test BBC playlist parsing with no music section."""
        mock_response = Mock()
        mock_response.text = mock_bbc_html_no_music
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        with pytest.raises(ValueError, match="Expecting 'Music Played' section"):
            parse_bbc_playlist("test_program_id")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_request_error(self, mock_get):
        """Test BBC playlist parsing with request error."""
        mock_get.side_effect = Exception("Network error")
        title, tracks, broadcast_date, description = parse_bbc_playlist("test_program_id")
        
        assert title == ""
        assert tracks == []
        assert broadcast_date == ""
        assert description == ""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_invalid_date(self, mock_get):
        """Test BBC playlist parsing with invalid date format."""
        html_with_invalid_date = """
        <html>
        <body>
            <h1>Test Programme</h1>
            <span class="broadcast-event__date">Invalid Date Format</span>
            <h2>Music Played</h2>
            <div class="segments-list">
                <li class="segments-list__item--music">
                    <div class="segment__track">
                        <h3 class="gamma no-margin">
                            <span class="artist">Artistoto</span>
                        </h3>
                        <span class="artist">Artist</span>
                        <p class="no-margin"><span>Track</span></p>
                    </div>
                </li>
            </div>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html_with_invalid_date
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        title, tracks, broadcast_date, description = parse_bbc_playlist("test_program_id")
        
        assert broadcast_date == ""  # Should handle invalid date gracefully

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_no_segments_list(self, mock_get):
        """Test BBC playlist parsing with no segments list."""
        html_no_segments = """
        <html>
        <body>
            <h1>Test Programme</h1>
            <h2>Music Played</h2>
            <div>No segments list here</div>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html_no_segments
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        with pytest.raises(ValueError, match="Expecting a track listing"):
            parse_bbc_playlist("test_program_id")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_no_music_items(self, mock_get):
        """Test BBC playlist parsing with no music items."""
        html_no_music_items = """
        <html>
        <body>
            <h1>Test Programme</h1>
            <h2>Music Played</h2>
            <div class="segments-list">
                <li class="segments-list__item--other">
                    <div>Not a music item</div>
                </li>
            </div>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html_no_music_items
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        with pytest.raises(ValueError, match="Cannot find music tracks"):
            parse_bbc_playlist("test_program_id")

class TestCreateYoutubePlaylist:
    """Tests for create_youtube_playlist function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    def test_create_youtube_playlist_success(
        self, mock_sleep, mock_add_tracks, mock_search_track, mock_create_playlist, 
        mock_get_ytmusic, mock_ytmusic, sample_tracks
    ):
        """Test successful YouTube playlist creation."""
        # Setup mocks
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        
        # Mock search to return matching results for each track
        def mock_search_side_effect(ytmusic, query, artist="", title=""):
            if "Artist One" in query:
                return {
                    'videoId': 'video_id_1',
                    'title': 'Track One',
                    'artists': [{'name': 'Artist One'}]
                }
            elif "Artist Two" in query:
                return {
                    'videoId': 'video_id_2',
                
    'title': 'Track Two',
                    'artists': [{'name': 'Artist Two'}]
                }
            elif "D'Angelo" in query:
                return {
                    'videoId': 'video_id_3',
                    'title': "Feel Like Makin' Love",
                    'artists': [{'name': "D'Angelo"}]
                }
            return None
        
        mock_search_track.side_effect = mock_search_side_effect
        mock_add_tracks.return_value = ([{'id': 'playlist_item_id'}], [])
        
        not_found = create_youtube_playlist("Test Playlist", sample_tracks)
        
        assert not_found == []
        mock_create_playlist.assert_called_once_with(mock_ytmusic, "Test Playlist", "")
        assert mock_search_track.call_count == 3
        mock_add_tracks.assert_called_once()

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    def test_create_youtube_playlist_with_prefix_and_date(
        self, mock_sleep, mock_search_track, mock_create_playlist, 
        mock_get_ytmusic, mock_ytmusic, sample_tracks
    ):
        """Test YouTube playlist creation with prefix and broadcast date."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_search_track.return_value = None  # No tracks found
        
        not_found = create_youtube_playlist(
            "Test Playlist", sample_tracks, 
            prefix="BBC6", broadcast_date="2025-12-27", description="Test description"
        )
        
        expected_title = "BBC6-2025-12-27: Test Playlist"
        mock_create_playlist.assert_called_once_with(mock_ytmusic, expected_title, "Test description")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    def test_create_youtube_playlist_not_found(
        self, mock_sleep, mock_search_track, mock_create_playlist, 
        mock_get_ytmusic, mock_ytmusic
    ):
        """Test YouTube playlist creation with unfound tracks."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_search_track.return_value = None  # Track not found
        
        tracks = [{"artist": "Unknown Artist", "title": "Unknown Track"}]
        not_found = create_youtube_playlist("Test Playlist", tracks)
        
        assert len(not_found) == 1
        assert not_found[0] == {"artist": "Unknown Artist", "title": "Unknown Track"}

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    def test_create_youtube_playlist_mismatched_tracks(
        self, mock_sleep, mock_add_tracks, mock_search_track, mock_create_playlist, 
        mock_get_ytmusic, mock_ytmusic
    ):
        """Test YouTube playlist creation with mismatched tracks."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_search_track.return_value = {
            'videoId': 'test_video_id',
            'title': 'Different Track',
            'artists': [{'name': 'Different Artist'}]
        }
        mock_add_tracks.return_value = ([{'id': 'playlist_item_id'}], [])
        
        tracks = [{"artist": "Original Artist", "title": "Original Track"}]
        not_found = create_youtube_playlist("Test Playlist", tracks)
        
        # Should be marked as not found due to mismatch
        assert len(not_found) == 1
        assert not_found[0] == {"artist": "Original Artist", "title": "Original Track"}

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    def test_create_youtube_playlist_add_tracks_error(
        self, mock_sleep, mock_add_tracks, mock_search_track, mock_create_playlist, 
        mock_get_ytmusic, mock_ytmusic, sample_tracks
    ):
        """Test YouTube playlist creation with errors during track addition."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_search_track.return_value = {
            'videoId': 'test_video_id',
            'title': 'Test Track',
            'artists': [{'name': 'Test Artist'}]
        }
        mock_add_tracks.side_effect = Exception("API Error")
        
        not_found = create_youtube_playlist("Test Playlist", sample_tracks)
        
        # Should fall back to individual track addition
        assert len(not_found) == 3  # All tracks should fail

class TestCreateYoutubePlaylistFromDraft:
    """Tests for create_youtube_playlist_from_draft function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    def test_create_youtube_playlist_from_draft_success(
        self, mock_add_tracks, mock_create_playlist, mock_get_ytmusic, 
        mock_ytmusic, sample_draft_tracks
    ):
        """Test successful YouTube playlist creation from draft."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_add_tracks.return_value = ([{'id': 'playlist_item_id'}], [])
        
        not_included = create_youtube_playlist_from_draft("Test Playlist", sample_draft_tracks)
        
        # Should only include tracks marked with include=True
        mock_add_tracks.assert_called_once_with(mock_ytmusic, 'test_playlist_id', ['video_id_1'])
        assert len(not_included) == 2  # Two tracks not included

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    def test_create_youtube_playlist_from_draft_no_tracks(
        self, mock_create_playlist, mock_get_ytmusic, mock_ytmusic
    ):
        """Test YouTube playlist creation from draft with no tracks to include."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        
        draft_tracks = [
            {
                "bbc_artist": "Artist",
                "bbc_title": "Track",
                "include": False,
                "video_id": "video_id"
            }
        ]
        
        not_included = create_youtube_playlist_from_draft("Test Playlist", draft_tracks)
        
        assert len(not_included) == 0  # Empty list returned when no tracks to add

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    def test_create_youtube_playlist_from_draft_with_prefix(
        self, mock_add_tracks, mock_create_playlist, mock_get_ytmusic, 
        mock_ytmusic, sample_draft_tracks
    ):
        """Test YouTube playlist creation from draft with prefix and date."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_add_tracks.return_value = ([{'id': 'playlist_item_id'}], [])
        
        create_youtube_playlist_from_draft(
            "Test Playlist", sample_draft_tracks, 
            prefix="BBC6", broadcast_date="2025-12-27", description="Test description"
        )
        
        expected_title = "BBC6-2025-12-27: Test Playlist"
        mock_create_playlist.assert_called_once_with(mock_ytmusic, expected_title, "Test description")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_or_find_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    def test_create_youtube_playlist_from_draft_add_error(
        self, mock_add_tracks, mock_create_playlist, mock_get_ytmusic, 
        mock_ytmusic, sample_draft_tracks
    ):
        """Test YouTube playlist creation from draft with add error."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('test_playlist_id', True)
        mock_add_tracks.side_effect = Exception("API Error")
        
        result = create_youtube_playlist_from_draft("Test Playlist", sample_draft_tracks)
        
        # Should return all tracks when error occurs
        assert len(result) == 3

class TestSaveDraft:
    """Tests for save_draft function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.strftime")
    def test_save_draft_success(
        self, mock_strftime, mock_file, mock_sleep, mock_search_track, 
        mock_get_ytmusic, mock_ytmusic, sample_tracks
    ):
        """Test successful draft saving."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_strftime.return_value = "2025-01-01 12:00:00"
        
        # Mock search to return matching results
        def mock_search_side_effect(ytmusic, query, artist="", title=""):
            if "Artist One" in query:
                return {
                    'videoId': 'video_id_1',
                    'title': 'Track One',
                    'artists': [{'name': 'Artist One'}]
                }
            elif "Artist Two" in query:
                return {
                    'videoId': 'video_id_2',
                    'title': 'Track Two',
                    'artists': [{'name': 'Artist Two'}]
                }
            elif "D'Angelo" in query:
                return {
                    'videoId': 'video_id_3',
                    'title': "Feel Like Makin' Love",
                    'artists': [{'name': "D'Angelo"}]
                }
            return None
        
        mock_search_track.side_effect = mock_search_side_effect
        
        # Capture the written data
        written_data = []
        def capture_write(data):
            written_data.append(data)
            return len(data)
        
        mock_file.return_value.write.side_effect = capture_write
        
        save_draft("Test Playlist", sample_tracks, "test_program", "test.json", "2025-12-27", "Test description")
        
        mock_file.assert_called_once_with("test.json", 'w', encoding='utf-8')
        # Verify JSON structure was written
        full_written_data = ''.join(written_data)
        assert '"playlist_title": "Test Playlist"' in full_written_data

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_draft_track_not_found(
        self, mock_file, mock_sleep, mock_search_track, 
        mock_get_ytmusic, mock_ytmusic
    ):
        """Test draft saving with tracks not found."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_search_track.return_value = None
        
        # Capture the written data
        written_data = []
        def capture_write(data):
            written_data.append(data)
            return len(data)
        
        mock_file.return_value.write.side_effect = capture_write
        
        tracks = [{"artist": "Unknown Artist", "title": "Unknown Track"}]
        save_draft("Test Playlist", tracks, "test_program", "test.json")
        
        full_written_data = ''.join(written_data)
        assert '"status": "not_found"' in full_written_data

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_ytmusic")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track_with_cache")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.time.sleep")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_draft_suspect_match(
        self, mock_file, mock_sleep, mock_search_track, 
        mock_get_ytmusic, mock_ytmusic
    ):
        """Test draft saving with suspect matches."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_search_track.return_value = {
            'videoId': 'test_video_id',
            'title': 'Different Track',
            'artists': [{'name': 'Different Artist'}]
        }
        
        # Capture the written data
        written_data = []
        def capture_write(data):
            written_data.append(data)
            return len(data)
        
        mock_file.return_value.write.side_effect = capture_write
        
        tracks = [{"artist": "Original Artist", "title": "Original Track"}]
        save_draft("Test Playlist", tracks, "test_program", "test.json")
        
        full_written_data = ''.join(written_data)
        assert '"status": "suspect_match"' in full_written_data
        assert '"include": false' in full_written_data

class TestLoadDraft:
    """Tests for load_draft function."""

    def test_load_draft_new_format(self, sample_draft_data):
        """Test loading draft with new format."""
        with patch("builtins.open", mock_open(read_data=json.dumps(sample_draft_data))):
            title, tracks, broadcast_date, description = load_draft("test.json")
            
            assert title == "Test Draft Playlist"
            assert len(tracks) == 3
            assert broadcast_date == "2025-12-27"
            assert description == "Test description"


    def test_load_draft_file_error(self):
        """Test loading draft with file error."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            with pytest.raises(SystemExit):
                load_draft("nonexistent.json")

    def test_load_draft_invalid_json(self):
        """Test loading draft with invalid JSON."""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            with pytest.raises(SystemExit):
                load_draft("invalid.json")

class TestMain:
    """Tests for main function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.save_draft")
    @patch("sys.argv", ["script", "draft", "test_program_id"])
    def test_main_draft_command(self, mock_save_draft, mock_parse_playlist, sample_tracks):
        """Test main function with draft command."""
        mock_parse_playlist.return_value = ("Test Playlist", sample_tracks, "2025-12-27", "Test description")
        
        with patch("sys.stderr", new_callable=StringIO):
            main()
        
        mock_save_draft.assert_called_once_with(
            "Test Playlist", sample_tracks, "test_program_id", "test_program_id.json", "2025-12-27", "Test description"
        )

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_youtube_playlist")
    @patch("sys.argv", ["script", "create", "--program-id", "test_program_id"])
    def test_main_create_command_with_program_id(self, mock_create_playlist, mock_parse_playlist, sample_tracks):
        """Test main function with create command using program ID."""
        mock_parse_playlist.return_value = ("Test Playlist", sample_tracks, "2025-12-27", "Test description")
        mock_create_playlist.return_value = []
        
        with patch("sys.stderr", new_callable=StringIO):
            main()
        
        mock_create_playlist.assert_called_once_with("Test Playlist", sample_tracks, None, "2025-12-27", "Test description")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.load_draft")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_youtube_playlist_from_draft")
    @patch("sys.argv", ["script", "create", "--draft", "test.json"])
    def test_main_create_command_with_draft(self, mock_create_from_draft, mock_load_draft, sample_draft_tracks):
        """Test main function with create command using draft file."""
        mock_load_draft.return_value = ("Test Playlist", sample_draft_tracks, "2025-12-27", "Test description")
        mock_create_from_draft.return_value = []
        
        with patch("sys.stderr", new_callable=StringIO):
            main()
        
        mock_create_from_draft.assert_called_once_with("Test Playlist", sample_draft_tracks, None, "2025-12-27", "Test description")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("sys.argv", ["script", "print", "--program-id", "test_program_id"])
    def test_main_print_command_with_program_id(self, mock_parse_playlist, sample_tracks):
        """Test main function with print command using program ID."""
        mock_parse_playlist.return_value = ("Test Playlist", sample_tracks, "2025-12-27", "Test description")
        
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch("sys.stderr", new_callable=StringIO):
                main()
        
        output = mock_stdout.getvalue()
        assert "1. Artist One - Track One" in output
        assert "2. Artist Two - Track Two" in output

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.load_draft")
    @patch("sys.argv", ["script", "print", "--draft", "test.json"])
    def test_main_print_command_with_draft(self, mock_load_draft, sample_draft_tracks):
        """Test main function with print command using draft file."""
        mock_load_draft.return_value = ("Test Playlist", sample_draft_tracks, "2025-12-27", "Test description")
        
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch("sys.stderr", new_callable=StringIO):
                main()
        
        output = mock_stdout.getvalue()
        assert "[✓] Artist One - Track One" in output
        assert "[?] Artist Two - Track Two" in output

    @patch("sys.argv", ["script"])
    def test_main_no_command(self):
        """Test main function with no command specified."""
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("sys.argv", ["script", "create"])
    def test_main_create_no_source(self):
        """Test main function with create command but no source specified."""
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("sys.argv", ["script", "create", "--program-id", "test_program_id"])
    def test_main_parse_failure(self, mock_parse_playlist):
        """Test main function when BBC playlist parsing fails."""
        mock_parse_playlist.return_value = ("", [], "", "")
        
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.load_draft")
    @patch("sys.argv", ["script", "create", "--draft", "test.json"])
    def test_main_load_draft_failure(self, mock_load_draft):
        """Test main function when draft loading fails."""
        mock_load_draft.return_value = ("", [], "", "")
        
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.save_draft")
    @patch("sys.argv", ["script", "draft", "test_program_id", "--output", "custom.json"])
    def test_main_draft_custom_output(self, mock_save_draft, mock_parse_playlist, sample_tracks):
        """Test main function with draft command and custom output filename."""
        mock_parse_playlist.return_value = ("Test Playlist", sample_tracks, "2025-12-27", "Test description")
        
        with patch("sys.stderr", new_callable=StringIO):
            main()
        
        mock_save_draft.assert_called_once_with(
            "Test Playlist", sample_tracks, "test_program_id", "custom.json", "2025-12-27", "Test description"
        )

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_youtube_playlist")
    @patch("sys.argv", ["script", "create", "--program-id", "test_program_id", "--prefix", "BBC6"])
    def test_main_create_with_prefix(self, mock_create_playlist, mock_parse_playlist, sample_tracks):
        """Test main function with create command and prefix."""
        mock_parse_playlist.return_value = ("Test Playlist", sample_tracks, "2025-12-27", "Test description")
        mock_create_playlist.return_value = []
        
        with patch("sys.stderr", new_callable=StringIO):
            main()
        
        mock_create_playlist.assert_called_once_with("Test Playlist", sample_tracks, "BBC6", "2025-12-27", "Test description")

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("sys.argv", ["script", "draft", "test_program_id"])
    def test_main_draft_parse_failure(self, mock_parse_playlist):
        """Test main function with draft command when parsing fails."""
        mock_parse_playlist.return_value = ("", [], "", "")
        
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("sys.argv", ["script", "print"])
    def test_main_print_no_source(self):
        """Test main function with print command but no source specified."""
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("sys.argv", ["script", "invalid_command"])
    def test_main_invalid_command(self):
        """Test main function with invalid command."""
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()

    @patch("sys.argv", ["script"])
    def test_main_no_args_shows_help(self):
        """Test main function with no arguments shows help and exits."""
        with patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit):
                main()
