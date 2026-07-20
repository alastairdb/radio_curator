"""Tests for YouTube Music API functions."""

import pytest
from unittest.mock import patch, Mock, mock_open
import os
from io import StringIO
import src.radio_curator.ytmusic_api
from src.radio_curator.ytmusic_api import (
    get_ytmusic, find_playlist, create_or_find_playlist, add_tracks_to_playlist,
    search_track, normalize_text, get_artist_names,
    search_track_with_cache, load_cache, save_cache, main, CACHE_DIR, CACHE_FILE
)

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
def sample_search_results():
    """Sample search results for testing."""
    return [
        {
            'videoId': 'video_id_1',
            'title': 'Test Track',
            'artists': [{'name': 'Test Artist'}]
        },
        {
            'videoId': 'video_id_2',
            'title': 'Another Track',
            'artists': [{'name': 'Another Artist'}]
        }
    ]

class TestCacheDirectory:
    """Tests for cache directory handling."""

    def test_cache_dir_uses_xdg_cache_home(self):
        """Test that cache directory respects XDG_CACHE_HOME environment variable."""
        with patch.dict(os.environ, {'XDG_CACHE_HOME': '/custom/cache'}):
            # Re-import to pick up the new environment variable
            import importlib
            import src.radio_curator.ytmusic_api
            importlib.reload(src.radio_curator.ytmusic_api)
            from src.radio_curator.ytmusic_api import CACHE_DIR
            assert CACHE_DIR == '/custom/cache/radio_curator'

    def test_cache_dir_defaults_to_dot_cache(self):
        """Test that cache directory defaults to ~/.cache when XDG_CACHE_HOME is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to pick up the cleared environment
            import importlib
            import src.radio_curator.ytmusic_api
            importlib.reload(src.radio_curator.ytmusic_api)
            from src.radio_curator.ytmusic_api import CACHE_DIR
            expected = os.path.join(os.path.expanduser('~'), '.cache', 'radio_curator')
            assert CACHE_DIR == expected

class TestGetYTMusic:
    """Tests for get_ytmusic function."""

    @patch("src.radio_curator.ytmusic_api.YTMusic")
    @patch("src.radio_curator.ytmusic_api.os.path.exists")
    def test_get_ytmusic_success(self, mock_exists, mock_ytmusic_class, mock_ytmusic):
        """Test successful YTMusic instance creation."""
        mock_exists.return_value = True
        mock_ytmusic_class.return_value = mock_ytmusic
        
        result = get_ytmusic()
        
        assert result == mock_ytmusic
        mock_ytmusic_class.assert_called_once()

    @patch("src.radio_curator.ytmusic_api.os.path.exists")
    def test_get_ytmusic_no_headers_file(self, mock_exists):
        """Test YTMusic instance creation when headers file doesn't exist."""
        mock_exists.return_value = False
        
        with pytest.raises(SystemExit):
            get_ytmusic()

class TestFindPlaylist:
    """Tests for find_playlist function."""

    def test_find_playlist_success(self, mock_ytmusic):
        """Test successful playlist finding."""
        mock_ytmusic.get_library_playlists.return_value = [
            {'title': 'Test Playlist', 'playlistId': 'test_id'},
            {'title': 'Another Playlist', 'playlistId': 'another_id'}
        ]
        
        result = find_playlist(mock_ytmusic, 'Test Playlist')
        
        assert result == 'test_id'

    def test_find_playlist_not_found(self, mock_ytmusic):
        """Test playlist finding when playlist doesn't exist."""
        mock_ytmusic.get_library_playlists.return_value = [
            {'title': 'Other Playlist', 'playlistId': 'other_id'}
        ]
        
        result = find_playlist(mock_ytmusic, 'Test Playlist')
        
        assert result is None

class TestCreateOrFindPlaylist:
    """Tests for create_or_find_playlist function."""

    @patch("src.radio_curator.ytmusic_api.find_playlist")
    def test_create_playlist_new(self, mock_find_playlist, mock_ytmusic):
        """Test creating a new playlist."""
        mock_find_playlist.return_value = None
        mock_ytmusic.create_playlist.return_value = 'new_playlist_id'
        
        playlist_id, was_created = create_or_find_playlist(mock_ytmusic, "New Playlist")
        
        assert playlist_id == 'new_playlist_id'
        assert was_created is True
        mock_ytmusic.create_playlist.assert_called_once_with("New Playlist", "", "PRIVATE")

    @patch("src.radio_curator.ytmusic_api.find_playlist")
    def test_create_playlist_existing(self, mock_find_playlist, mock_ytmusic):
        """Test finding an existing playlist."""
        mock_find_playlist.return_value = 'existing_playlist_id'
        
        playlist_id, was_created = create_or_find_playlist(mock_ytmusic, "Existing Playlist")
        
        assert playlist_id == 'existing_playlist_id'
        assert was_created is False
        mock_ytmusic.create_playlist.assert_not_called()

class TestAddTracksToPlaylist:
    """Tests for add_tracks_to_playlist function."""

    def test_add_tracks_success(self, mock_ytmusic):
        """Test successful track addition."""
        mock_ytmusic.add_playlist_items.return_value = {'status': 'success'}
        
        responses, errors = add_tracks_to_playlist(mock_ytmusic, 'playlist_id', ['video_id_1', 'video_id_2'])
        
        assert len(responses) == 1
        assert len(errors) == 0
        mock_ytmusic.add_playlist_items.assert_called_once_with('playlist_id', ['video_id_1', 'video_id_2'])

    def test_add_tracks_batch_error_fallback_success(self, mock_ytmusic):
        """Test track addition with batch error but individual success."""
        # First call (batch) fails, subsequent calls (individual) succeed
        mock_ytmusic.add_playlist_items.side_effect = [
            Exception("Batch error"),
            {'status': 'success'},
            {'status': 'success'}
        ]
        
        responses, errors = add_tracks_to_playlist(mock_ytmusic, 'playlist_id', ['video_id_1', 'video_id_2'])
        
        assert len(responses) == 2
        assert len(errors) == 0
        assert mock_ytmusic.add_playlist_items.call_count == 3

    def test_add_tracks_individual_errors(self, mock_ytmusic):
        """Test track addition with individual errors."""
        mock_ytmusic.add_playlist_items.side_effect = [
            Exception("Batch error"),
            Exception("Individual error 1"),
            Exception("Individual error 2")
        ]
        
        responses, errors = add_tracks_to_playlist(mock_ytmusic, 'playlist_id', ['video_id_1', 'video_id_2'])
        
        assert len(responses) == 0
        assert len(errors) == 2
        assert errors[0] == ('video_id_1', 'Individual error 1')
        assert errors[1] == ('video_id_2', 'Individual error 2')

class TestCacheFunctions:
    """Tests for cache load/save functions."""

    def test_load_cache_success(self, monkeypatch):
        """Test successful cache loading."""
        # Mock os.path.exists to return True
        monkeypatch.setattr("src.radio_curator.ytmusic_api.os.path.exists", lambda x: True)
        
        # Mock open to return test data
        mock_file = mock_open(read_data='{"test query": "test_video_id"}')
        monkeypatch.setattr("builtins.open", mock_file)
        
        # Clear cache before test
        src.radio_curator.ytmusic_api._search_cache.clear()
        
        load_cache()
        assert "test query" in src.radio_curator.ytmusic_api._search_cache
        assert src.radio_curator.ytmusic_api._search_cache["test query"] == "test_video_id"

    def test_load_cache_file_not_exists(self, monkeypatch):
        """Test cache loading when file doesn't exist."""
        # Mock os.path.exists to return False
        monkeypatch.setattr("src.radio_curator.ytmusic_api.os.path.exists", lambda x: False)
        
        # Clear cache before test
        src.radio_curator.ytmusic_api._search_cache.clear()
        
        load_cache()
        assert len(src.radio_curator.ytmusic_api._search_cache) == 0

    def test_load_cache_exception_handling(self, monkeypatch):
        """Test that load_cache handles exceptions gracefully."""
        # Mock os.path.exists to return True
        monkeypatch.setattr("src.radio_curator.ytmusic_api.os.path.exists", lambda x: True)
        
        # Mock open to raise an OSError (load_cache catches OSError)
        def mock_open_exception(*args, **kwargs):
            raise OSError("File error")
        monkeypatch.setattr("builtins.open", mock_open_exception)
        
        # Set up cache with existing data
        src.radio_curator.ytmusic_api._search_cache.clear()
        src.radio_curator.ytmusic_api._search_cache["existing"] = "value"
        
        load_cache()
        # Cache should be cleared on exception
        assert len(src.radio_curator.ytmusic_api._search_cache) == 0

    @patch("src.radio_curator.ytmusic_api.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_cache_success(self, mock_file, mock_makedirs):
        """Test successful cache saving."""
        # Set up test data
        src.radio_curator.ytmusic_api._search_cache["test query"] = "test_video_id"
        
        save_cache()
        mock_makedirs.assert_called_once_with(CACHE_DIR, exist_ok=True)
        mock_file.assert_called_once_with(CACHE_FILE, 'w', encoding='utf-8')

    @patch("src.radio_curator.ytmusic_api.os.makedirs")
    @patch("builtins.open")
    def test_save_cache_exception_handling(self, mock_file, mock_makedirs):
        """Test that save_cache handles exceptions gracefully."""
        mock_makedirs.side_effect = OSError("Permission denied")
        
        # Set up test data
        src.radio_curator.ytmusic_api._search_cache["test query"] = "test_video_id"
        
        # Should not raise an exception
        save_cache()

class TestSearchTrack:
    """Tests for search_track function."""

    def test_search_track_songs_success(self, mock_ytmusic, sample_search_results):
        """Test successful track search in songs."""
        mock_ytmusic.search.return_value = sample_search_results
        
        result = search_track(mock_ytmusic, "test query")
        
        assert result == sample_search_results[0]
        mock_ytmusic.search.assert_any_call("test query", filter="songs", limit=5)

    def test_search_track_videos_fallback(self, mock_ytmusic, sample_search_results):
        """Test track search falling back to videos when no songs found."""
        mock_ytmusic.search.side_effect = [[], sample_search_results]
        
        result = search_track(mock_ytmusic, "test query")
        
        assert result == sample_search_results[0]
        assert mock_ytmusic.search.call_count == 2

    def test_search_track_no_results(self, mock_ytmusic):
        """Test track search with no results."""
        mock_ytmusic.search.return_value = []
        
        result = search_track(mock_ytmusic, "test query")
        
        assert result is None

class TestSearchTrackWithCache:
    """Tests for search_track_with_cache function."""

    @patch("src.radio_curator.ytmusic_api.load_cache")
    @patch("src.radio_curator.ytmusic_api.save_cache")
    @patch("src.radio_curator.ytmusic_api.search_track")
    def test_search_track_with_cache_success(self, mock_search_track, mock_save_cache, mock_load_cache, mock_ytmusic, sample_search_results):
        """Test track search with successful caching."""
        mock_search_track.return_value = sample_search_results[0]
        
        result = search_track_with_cache(mock_ytmusic, "test query")
        
        assert result == sample_search_results[0]
        mock_save_cache.assert_called_once()

    @patch("src.radio_curator.ytmusic_api.load_cache")
    @patch("src.radio_curator.ytmusic_api.save_cache")
    @patch("src.radio_curator.ytmusic_api.search_track")
    def test_search_track_no_results_with_cache(self, mock_search_track, mock_save_cache, mock_load_cache, mock_ytmusic):
        """Test track search with no results and caching."""
        mock_search_track.return_value = None
        
        result = search_track_with_cache(mock_ytmusic, "test query")
        
        assert result is None
        mock_save_cache.assert_not_called()

    @patch("src.radio_curator.ytmusic_api.search_track")
    def test_search_track_cached_result(self, mock_search_track, mock_ytmusic, sample_search_results):
        """Test track search returning cached result."""
        from src.radio_curator.ytmusic_api import _search_cache
        _search_cache['test query'] = 'cached_video_id'
        
        # Mock search_track to return a result with the cached video ID
        mock_search_track.return_value = sample_search_results[0]
        sample_search_results[0]['videoId'] = 'cached_video_id'
        
        result = search_track_with_cache(mock_ytmusic, "test query")
        
        assert result == sample_search_results[0]

class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        result = normalize_text("Test String")
        assert result == "test string"

    def test_normalize_text_accents(self):
        """Test accent removal."""
        result = normalize_text("café naïve résumé")
        assert result == "cafe naive resume"

    def test_normalize_text_special_chars(self):
        """Test special character replacement."""
        result = normalize_text("Michał")
        assert result == "michal"

    def test_normalize_text_empty(self):
        """Test empty string normalization."""
        result = normalize_text("")
        assert result == ""

    def test_normalize_text_none(self):
        """Test None input."""
        result = normalize_text(None)
        assert result == ""

class TestGetArtistNames:
    """Tests for get_artist_names function."""

    def test_get_artist_names_single(self):
        """Test extracting single artist name."""
        result_data = {'artists': [{'name': 'Test Artist'}]}
        result = get_artist_names(result_data)
        assert result == "Test Artist"

    def test_get_artist_names_multiple(self):
        """Test extracting multiple artist names."""
        result_data = {'artists': [{'name': 'Artist One'}, {'name': 'Artist Two'}]}
        result = get_artist_names(result_data)
        assert result == "Artist One, Artist Two"

    def test_get_artist_names_no_artists(self):
        """Test when no artists are present."""
        result_data = {'artists': []}
        result = get_artist_names(result_data)
        assert result == "Unknown Artist"

class TestMain:
    """Tests for main function."""

    @patch("src.radio_curator.ytmusic_api.setup")
    @patch("src.radio_curator.ytmusic_api.os.makedirs")
    @patch("sys.argv", ["ytmusic_api.py", "setup"])
    def test_main_setup_command(self, mock_makedirs, mock_setup):
        """Test main function with setup command."""
        with patch("sys.stdout", new_callable=StringIO):
            main()
        
        mock_makedirs.assert_called_once()
        mock_setup.assert_called_once()

    @patch("src.radio_curator.ytmusic_api.get_ytmusic")
    @patch("src.radio_curator.ytmusic_api.create_or_find_playlist")
    @patch("sys.argv", ["ytmusic_api.py", "create-playlist", "Test Playlist"])
    def test_main_create_playlist(self, mock_create_playlist, mock_get_ytmusic, mock_ytmusic):
        """Test main function with create-playlist command."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_create_playlist.return_value = ('playlist_id', True)
        
        with patch("sys.stdout", new_callable=StringIO):
            main()
        
        mock_create_playlist.assert_called_once_with(mock_ytmusic, "Test Playlist", "", "PRIVATE")

    @patch("src.radio_curator.ytmusic_api.get_ytmusic")
    @patch("src.radio_curator.ytmusic_api.search_track_with_cache")
    @patch("sys.argv", ["ytmusic_api.py", "search-track", "test query"])
    def test_main_search_track(self, mock_search_track, mock_get_ytmusic, mock_ytmusic, sample_search_results):
        """Test main function with search-track command."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_search_track.return_value = sample_search_results[0]
        
        with patch("sys.stdout", new_callable=StringIO):
            main()
        
        mock_search_track.assert_called_once_with(mock_ytmusic, "test query")

    @patch("src.radio_curator.ytmusic_api.get_ytmusic")
    @patch("src.radio_curator.ytmusic_api.add_tracks_to_playlist")
    @patch("sys.argv", ["ytmusic_api.py", "add-track", "playlist_id", "video_id"])
    def test_main_add_track(self, mock_add_tracks, mock_get_ytmusic, mock_ytmusic):
        """Test main function with add-track command."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_add_tracks.return_value = (['response'], [])

        with patch("sys.stdout", new_callable=StringIO):
            main()

        mock_add_tracks.assert_called_once_with(mock_ytmusic, "playlist_id", ["video_id"])

    @patch("src.radio_curator.ytmusic_api.get_ytmusic")
    @patch("src.radio_curator.ytmusic_api.search_track_with_cache")
    @patch("sys.argv", ["ytmusic_api.py", "print-tracks", "query1, query2"])
    def test_main_print_tracks(self, mock_search_track, mock_get_ytmusic, mock_ytmusic, sample_search_results):
        """Test main function with print-tracks command."""
        mock_get_ytmusic.return_value = mock_ytmusic
        mock_search_track.return_value = sample_search_results[0]

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main()

        output = mock_stdout.getvalue()
        assert "Track 1/2: query1" in output
        assert "Track 2/2: query2" in output
        assert mock_search_track.call_count == 2

    @patch("sys.argv", ["ytmusic_api.py"])
    def test_main_no_command(self):
        """Test main function with no command."""
        with patch("sys.stdout", new_callable=StringIO):
            main()  # Should print help and return
