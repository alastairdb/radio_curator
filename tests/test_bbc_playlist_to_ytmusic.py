"""Tests for BBC playlist to YouTube Music conversion."""

import pytest
from unittest.mock import patch, Mock
import sys
from io import StringIO
from src.gp2ytm.bbc_playlist_to_ytmusic import (
    parse_bbc_playlist, create_youtube_playlist, main
)

@pytest.fixture
def mock_bbc_html():
    """Sample BBC HTML content for testing."""
    return """
    <html>
    <head><title>Test BBC Programme</title></head>
    <body>
        <h1>Test BBC Programme Title</h1>
        <h2>Music Played</h2>
        <div class="segments-list">
            <li>
                <h3>Artist One</h3>
                <div>Track One</div>
            </li>
            <li>
                <h3>Artist Two</h3>
                <div>Track Two</div>
            </li>
        </div>
    </body>
    </html>
    """

@pytest.fixture
def mock_youtube_service():
    """Create a mock YouTube service."""
    return Mock()

class TestParseBbcPlaylist:
    """Tests for parse_bbc_playlist function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_success(self, mock_get, mock_bbc_html):
        """Test successful BBC playlist parsing."""
        mock_response = Mock()
        mock_response.text = mock_bbc_html
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        title, tracks = parse_bbc_playlist("test_program_id")
        
        assert title == "Test BBC Programme Title"
        assert len(tracks) == 2
        assert tracks[0] == {"artist": "Artist One", "title": "Track One"}
        assert tracks[1] == {"artist": "Artist Two", "title": "Track Two"}

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.requests.get")
    def test_parse_bbc_playlist_request_error(self, mock_get):
        """Test BBC playlist parsing with request error."""
        mock_get.side_effect = Exception("Network error")
        title, tracks = parse_bbc_playlist("test_program_id")
        
        assert title == ""
        assert tracks == []

class TestCreateYoutubePlaylist:
    """Tests for create_youtube_playlist function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_credentials")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.build")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.add_tracks_to_playlist")
    def test_create_youtube_playlist_success(
        self, mock_add_tracks, mock_search_track, mock_create_playlist, 
        mock_build, mock_get_credentials, mock_youtube_service
    ):
        """Test successful YouTube playlist creation."""
        # Setup mocks
        mock_get_credentials.return_value = Mock()
        mock_build.return_value = mock_youtube_service
        mock_create_playlist.return_value = {'id': 'test_playlist_id'}
        mock_search_track.return_value = 'test_video_id'
        mock_add_tracks.return_value = ([{'id': 'playlist_item_id'}], [])
        
        tracks = [
            {"artist": "Artist One", "title": "Track One"},
            {"artist": "Artist Two", "title": "Track Two"}
        ]
        
        not_found = create_youtube_playlist("Test Playlist", tracks)
        
        assert not_found == []
        mock_create_playlist.assert_called_once()
        assert mock_search_track.call_count == 2
        mock_add_tracks.assert_called_once()

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.get_credentials")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.build")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.search_track")
    def test_create_youtube_playlist_not_found(
        self, mock_search_track, mock_create_playlist, 
        mock_build, mock_get_credentials, mock_youtube_service
    ):
        """Test YouTube playlist creation with unfound tracks."""
        # Setup mocks
        mock_get_credentials.return_value = Mock()
        mock_build.return_value = mock_youtube_service
        mock_create_playlist.return_value = {'id': 'test_playlist_id'}
        mock_search_track.return_value = None  # Track not found
        
        tracks = [{"artist": "Unknown Artist", "title": "Unknown Track"}]
        
        not_found = create_youtube_playlist("Test Playlist", tracks)
        
        assert len(not_found) == 1
        assert not_found[0] == {"artist": "Unknown Artist", "title": "Unknown Track"}

class TestMain:
    """Tests for main function."""

    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.parse_bbc_playlist")
    @patch("src.gp2ytm.bbc_playlist_to_ytmusic.create_youtube_playlist")
    def test_main_success(self, mock_create_playlist, mock_parse_playlist):
        """Test main function success case."""
        # Setup mocks
        mock_parse_playlist.return_value = (
            "Test Playlist", 
            [{"artist": "Artist", "title": "Track"}]
        )
        mock_create_playlist.return_value = []
        
        # Capture stderr
        captured_output = StringIO()
        sys.stderr = captured_output
        
        # Test with program ID
        sys.argv = ['bbc_playlist_to_ytmusic.py', 'test_program_id']
        try:
            main()
        except SystemExit:
            pass
        
        # Restore stderr
        sys.stderr = sys.__stderr__
        
        output = captured_output.getvalue()
        assert 'Found playlist: Test Playlist' in output
        assert 'Found 1 tracks' in output

    def test_main_wrong_args(self):
        """Test main function with wrong number of arguments."""
        # Capture stderr
        captured_output = StringIO()
        sys.stderr = captured_output
        
        # Test with wrong number of arguments
        sys.argv = ['bbc_playlist_to_ytmusic.py']
        try:
            main()
        except SystemExit:
            pass
        
        # Restore stderr
        sys.stderr = sys.__stderr__
        
        output = captured_output.getvalue()
        assert 'Usage: python bbc_playlist_to_ytmusic.py' in output
