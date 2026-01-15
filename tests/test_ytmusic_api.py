"""Tests for YouTube Music API functions."""

import pytest
from unittest.mock import patch, Mock, mock_open
import sys
import os
from io import StringIO
import src.gp2ytm.ytmusic_api
from src.gp2ytm.ytmusic_api import (
    get_credentials, create_or_find_playlist, add_tracks_to_playlist, 
    search_track_with_cache, main, load_cache, save_cache, CACHE_DIR, CACHE_FILE
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

class TestCacheDirectory:
    """Tests for cache directory handling."""

    def test_cache_dir_uses_xdg_cache_home(self):
        """Test that cache directory respects XDG_CACHE_HOME environment variable."""
        with patch.dict(os.environ, {'XDG_CACHE_HOME': '/custom/cache'}):
            # Re-import to pick up the new environment variable
            import importlib
            import src.gp2ytm.ytmusic_api
            importlib.reload(src.gp2ytm.ytmusic_api)
            from src.gp2ytm.ytmusic_api import CACHE_DIR
            assert CACHE_DIR == '/custom/cache/gp2ytm'

    def test_cache_dir_defaults_to_dot_cache(self):
        """Test that cache directory defaults to ~/.cache when XDG_CACHE_HOME is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to pick up the cleared environment
            import importlib
            import src.gp2ytm.ytmusic_api
            importlib.reload(src.gp2ytm.ytmusic_api)
            from src.gp2ytm.ytmusic_api import CACHE_DIR
            expected = os.path.join(os.path.expanduser('~'), '.cache', 'gp2ytm')
            assert CACHE_DIR == expected

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

class TestCreateOrFindPlaylist:
    """Tests for create_or_find_playlist function."""

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
        
        result, was_created = create_or_find_playlist(
            mock_youtube_service, 
            'Test Playlist', 
            'Test Description',
            'private'
        )
        
        assert result == 'test_playlist_id'
        assert was_created
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

class TestCacheFunctions:
    """Tests for cache load/save functions."""

    def test_load_cache_success(self, monkeypatch):
        """Test successful cache loading."""
        # Mock os.path.exists to return True
        monkeypatch.setattr("src.gp2ytm.ytmusic_api.os.path.exists", lambda x: True)
        
        # Mock open to return test data
        mock_file = mock_open(read_data='{"test query": "test_video_id"}')
        monkeypatch.setattr("builtins.open", mock_file)
        
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        load_cache()
        assert "test query" in src.gp2ytm.ytmusic_api._search_cache
        assert src.gp2ytm.ytmusic_api._search_cache["test query"] == "test_video_id"

    def test_load_cache_file_not_exists(self, monkeypatch):
        """Test cache loading when file doesn't exist."""
        # Mock os.path.exists to return False
        monkeypatch.setattr("src.gp2ytm.ytmusic_api.os.path.exists", lambda x: False)
        
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        load_cache()
        assert len(src.gp2ytm.ytmusic_api._search_cache) == 0

    def test_load_cache_exception_handling(self, monkeypatch):
        """Test that load_cache handles exceptions gracefully."""
        # Mock os.path.exists to return True
        monkeypatch.setattr("src.gp2ytm.ytmusic_api.os.path.exists", lambda x: True)
        
        # Mock open to raise an exception
        def mock_open_exception(*args, **kwargs):
            raise Exception("File error")
        monkeypatch.setattr("builtins.open", mock_open_exception)
        
        # Set up cache with existing data
        src.gp2ytm.ytmusic_api._search_cache.clear()
        src.gp2ytm.ytmusic_api._search_cache["existing"] = "value"
        
        load_cache()
        # Cache should be cleared on exception
        assert len(src.gp2ytm.ytmusic_api._search_cache) == 0

    @patch("src.gp2ytm.ytmusic_api.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_cache_success(self, mock_file, mock_makedirs):
        """Test successful cache saving."""
        # Set up test data
        src.gp2ytm.ytmusic_api._search_cache["test query"] = "test_video_id"
        
        save_cache()
        mock_makedirs.assert_called_once_with(CACHE_DIR, exist_ok=True)
        mock_file.assert_called_once_with(CACHE_FILE, 'w')

    @patch("src.gp2ytm.ytmusic_api.os.makedirs")
    @patch("builtins.open")
    def test_save_cache_exception_handling(self, mock_file, mock_makedirs):
        """Test that save_cache handles exceptions gracefully."""
        mock_makedirs.side_effect = Exception("Permission denied")
        
        # Set up test data
        src.gp2ytm.ytmusic_api._search_cache["test query"] = "test_video_id"
        
        # Should not raise an exception
        save_cache()

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
        
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        # Import the search_track function directly to test it
        from src.gp2ytm.ytmusic_api import search_track
        result = search_track(mock_youtube_service, 'test query')
        assert result == 'test_video_id'

    def test_search_track_no_results(self, mock_youtube_service):
        """Test track search with no results."""
        mock_response = {'items': []}
        mock_youtube_service.search().list().execute.return_value = mock_response
        
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        # Import the search_track function directly to test it
        from src.gp2ytm.ytmusic_api import search_track
        result = search_track(mock_youtube_service, 'test query')
        assert result is None

    @patch("src.gp2ytm.ytmusic_api.load_cache")
    @patch("src.gp2ytm.ytmusic_api.save_cache")
    def test_search_track_with_cache_success(self, mock_save_cache, mock_load_cache, mock_youtube_service):
        """Test successful track search with caching."""
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        # Mock the search_track function to return a result
        with patch("src.gp2ytm.ytmusic_api.search_track", return_value="test_video_id"):
            result = search_track_with_cache(mock_youtube_service, 'test query')
            assert result == 'test_video_id'

    @patch("src.gp2ytm.ytmusic_api.load_cache")
    @patch("src.gp2ytm.ytmusic_api.save_cache")
    def test_search_track_no_results_with_cache(self, mock_save_cache, mock_load_cache, mock_youtube_service):
        """Test track search with no results and caching."""
        # Clear cache before test
        src.gp2ytm.ytmusic_api._search_cache.clear()
        
        # Mock the search_track function to return None
        with patch("src.gp2ytm.ytmusic_api.search_track", return_value=None):
            result = search_track_with_cache(mock_youtube_service, 'test query')
            assert result is None

    def test_search_track_cached_result(self, mock_youtube_service):
        """Test that cached results are returned without API call."""
        # Set up cache with test data
        src.gp2ytm.ytmusic_api._search_cache["cached query"] = "cached_video_id"
        
        # Mock search_track to ensure it's not called
        with patch("src.gp2ytm.ytmusic_api.search_track") as mock_search:
            result = search_track_with_cache(mock_youtube_service, 'cached query')
            assert result == 'cached_video_id'
            # Verify search_track was not called
            mock_search.assert_not_called()

class TestMain:
    """Tests for main function."""

    @patch("src.gp2ytm.ytmusic_api.get_credentials")
    @patch("src.gp2ytm.ytmusic_api.build")
    @patch("src.gp2ytm.ytmusic_api.create_or_find_playlist")
    def test_main_create_playlist(self, mock_create_playlist, mock_build, mock_get_credentials, mock_credentials):
        """Test main function with create-playlist command."""
        mock_get_credentials.return_value = mock_credentials
        mock_build.return_value = Mock()
        mock_create_playlist.return_value = ('test_playlist_id', True)
        
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
    @patch("src.gp2ytm.ytmusic_api.search_track_with_cache")
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
