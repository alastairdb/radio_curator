"""Tests for YouTube Music API functions."""

import pytest
from unittest.mock import patch, Mock, mock_open
import sys
from io import StringIO
from src.gp2ytm.ytmusic_api import (
    get_credentials, create_playlist, add_tracks_to_playlist, 
    search_track, main
)

@pytest.fixture
def mock_youtube_service():
    """Create a mock YouTube service."""
    return Mock()

@pytest.fixture
def mock_credentials():
    """Create mock credentials."""
    creds = Mock()
    creds.valid = True
    creds.expired = False
    return creds

class TestGetCredentials:
    """Tests for get_credentials function."""

    @patch("src.gp2ytm.ytmusic_api.Credentials.from_authorized_user_file")
    @patch("src.gp2ytm.ytmusic_api.os.path.exists")
    def test_get_credentials_existing_valid(self, mock_exists, mock_from_file, mock_credentials):
        """Test getting existing valid credentials."""
        mock_exists.return_value = True
        mock_from_file.return_value = mock_credentials
        
        creds = get_credentials()
        assert creds == mock_credentials

    @patch("src.gp2ytm.ytmusic_api.InstalledAppFlow")
    @patch("src.gp2ytm.ytmusic_api.Credentials.from_authorized_user_file")
    @patch("src.gp2ytm.ytmusic_api.os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_credentials_new_login(self, mock_file, mock_exists, mock_from_file, mock_flow, mock_credentials):
        """Test getting credentials with new login."""
        mock_exists.return_value = False
        mock_flow_instance = Mock()
        mock_flow_instance.run_local_server.return_value = mock_credentials
        mock_flow.from_client_secrets_file.return_value = mock_flow_instance
        
        creds = get_credentials()
        assert creds == mock_credentials
        mock_flow_instance.run_local_server.assert_called_once_with(port=0)

class TestCreatePlaylist:
    """Tests for create_playlist function."""

    def test_create_playlist_success(self, mock_youtube_service):
        """Test successful playlist creation."""
        mock_response = {
            'id': 'test_playlist_id',
            'snippet': {
                'title': 'Test Playlist',
                'description': 'Test Description'
            }
        }
        mock_youtube_service.playlists().insert().execute.return_value = mock_response
        
        result = create_playlist(
            mock_youtube_service, 
            'Test Playlist', 
            'Test Description',
            'private'
        )
        
        assert result == mock_response
        mock_youtube_service.playlists().insert().execute.assert_called_once()

class TestAddTracksToPlaylist:
    """Tests for add_tracks_to_playlist function."""

    def test_add_tracks_success(self, mock_youtube_service):
        """Test successful track addition."""
        mock_response = {'id': 'playlist_item_id'}
        mock_youtube_service.playlistItems().insert().execute.return_value = mock_response
        
        responses, errors = add_tracks_to_playlist(
            mock_youtube_service, 
            'test_playlist_id', 
            ['video1', 'video2']
        )
        
        assert len(responses) == 2
        assert len(errors) == 0
        assert responses[0] == mock_response
        assert mock_youtube_service.playlistItems().insert().execute.call_count == 2

    def test_add_tracks_with_error(self, mock_youtube_service):
        """Test track addition with errors."""
        mock_response = {'id': 'playlist_item_id'}
        mock_youtube_service.playlistItems().insert().execute.side_effect = [
            mock_response,
            Exception("API Error")
        ]
        
        responses, errors = add_tracks_to_playlist(
            mock_youtube_service, 
            'test_playlist_id', 
            ['video1', 'video2']
        )
        
        assert len(responses) == 1
        assert len(errors) == 1
        assert errors[0] == ('video2', 'API Error')

class TestSearchTrack:
    """Tests for search_track function."""

    def test_search_track_success(self, mock_youtube_service):
        """Test successful track search."""
        mock_response = {
            'items': [{
                'id': {'videoId': 'test_video_id'},
                'snippet': {'title': 'Test Track Official Audio'}
            }]
        }
        mock_youtube_service.search().list().execute.return_value = mock_response
        
        result = search_track(mock_youtube_service, 'test query')
        assert result == 'test_video_id'

    def test_search_track_no_results(self, mock_youtube_service):
        """Test track search with no results."""
        mock_response = {'items': []}
        mock_youtube_service.search().list().execute.return_value = mock_response
        
        result = search_track(mock_youtube_service, 'test query')
        assert result is None

    def test_search_track_fallback(self, mock_youtube_service):
        """Test track search with fallback to first result."""
        # First attempts return no matching results
        mock_empty = {'items': []}
        
        # Final attempt returns a result
        mock_fallback = {
            'items': [{
                'id': {'videoId': 'fallback_video_id'},
                'snippet': {'title': 'Fallback Track'}
            }]
        }
        
        mock_youtube_service.search().list().execute.side_effect = [
            mock_empty,  # "official audio" search
            mock_empty,  # "music" search
            mock_empty,  # "official music video" search
            mock_fallback  # fallback search
        ]
        
        result = search_track(mock_youtube_service, 'test query')
        assert result == 'fallback_video_id'

class TestMain:
    """Tests for main function."""

    @patch("src.gp2ytm.ytmusic_api.get_credentials")
    @patch("src.gp2ytm.ytmusic_api.build")
    @patch("src.gp2ytm.ytmusic_api.create_playlist")
    def test_main_create_playlist(self, mock_create_playlist, mock_build, mock_get_credentials, mock_credentials):
        """Test main function with create-playlist command."""
        mock_get_credentials.return_value = mock_credentials
        mock_build.return_value = Mock()
        mock_create_playlist.return_value = {
            'id': 'test_playlist_id',
            'snippet': {'title': 'Test Playlist'}
        }
        
        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        # Test with create-playlist command
        sys.argv = ['ytmusic_api.py', 'create-playlist', 'Test Playlist']
        try:
            main()
        except SystemExit:
            pass
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert 'Created playlist: Test Playlist' in output
        assert 'Playlist ID: test_playlist_id' in output

    @patch("src.gp2ytm.ytmusic_api.get_credentials")
    @patch("src.gp2ytm.ytmusic_api.build")
    @patch("src.gp2ytm.ytmusic_api.search_track")
    def test_main_search_track(self, mock_search_track, mock_build, mock_get_credentials, mock_credentials):
        """Test main function with search-track command."""
        mock_get_credentials.return_value = mock_credentials
        mock_build.return_value = Mock()
        mock_search_track.return_value = 'test_video_id'
        
        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        # Test with search-track command
        sys.argv = ['ytmusic_api.py', 'search-track', 'test query']
        try:
            main()
        except SystemExit:
            pass
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert 'Found track ID: test_video_id' in output

    def test_main_no_command(self):
        """Test main function with no command."""
        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        # Test with no command
        sys.argv = ['ytmusic_api.py']
        try:
            main()
        except SystemExit:
            pass
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert 'usage: ytmusic_api.py' in output
