"""Tests for main entry point."""

from unittest.mock import patch, MagicMock, call
import sys
import os
from io import StringIO
import pytest
# Import mutagen classes for isinstance checks
try:
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
except ImportError:
    # Create dummy classes if mutagen is not installed (though it should be)
    class ID3: pass
    class MP4: pass
    class FLAC: pass

from src.radio_curator.main import (
    main as main_entry,
    check_ip_location,
    format_playlist_for_lyrics,
    add_playlist_to_audio_metadata,
    find_downloaded_audio_files,
    move_files_to_jellyfin,
    trigger_jellyfin_rescan,
    download_radio_show
)

class TestMainEntryPoint:
    """Tests for main entry point."""

    def test_main_no_args(self):
        """Test main with no arguments."""
        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        # Test with no arguments
        sys.argv = ['radio_curator']
        main_entry()
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert 'usage: radio_curator' in output
        assert 'Available commands' in output

    @patch("src.radio_curator.main.ytmusic_api_main")
    def test_main_ytmusic_api_command(self, mock_ytmusic_main):
        """Test main with ytmusic-api command."""
        # Test with ytmusic-api command
        sys.argv = ['radio_curator', 'ytmusic-api', 'create-playlist', 'Test']
        main_entry()
        
        # Check that ytmusic_api_main was called
        mock_ytmusic_main.assert_called_once()
        # Check that argv was modified correctly
        assert sys.argv == ['radio_curator', 'create-playlist', 'Test']

    @patch("src.radio_curator.main.bbc_playlist_main")
    def test_main_bbc_playlist_command(self, mock_bbc_main):
        """Test main with bbc-playlist command."""
        # Test with bbc-playlist command
        sys.argv = ['radio_curator', 'bbc-playlist', 'test_program_id']
        main_entry()
        
        # Check that bbc_playlist_main was called
        mock_bbc_main.assert_called_once()
        # Check that argv was modified correctly
        assert sys.argv == ['radio_curator', 'test_program_id']

    def test_main_unknown_command(self):
        """Test main with unknown command."""
        # Capture stderr
        captured_stderr = StringIO()
        sys.stderr = captured_stderr
        
        # Test with unknown command
        sys.argv = ['radio_curator', 'unknown-command']
        
        # Expect SystemExit
        with pytest.raises(SystemExit) as excinfo:
            main_entry()
        
        # Restore stderr
        sys.stderr = sys.__stderr__
        
        assert excinfo.value.code == 2
        output = captured_stderr.getvalue()
        assert "invalid choice: 'unknown-command'" in output

class TestHelperFunctions:
    """Tests for helper functions in main.py."""

    @patch("src.radio_curator.main.requests.get")
    def test_check_ip_location_gb(self, mock_get):
        """Test check_ip_location when in GB."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"country": "GB"}
        mock_get.return_value = mock_response
        
        is_gb, country = check_ip_location()
        
        assert is_gb is True
        assert country == "GB"

    @patch("src.radio_curator.main.requests.get")
    def test_check_ip_location_other(self, mock_get):
        """Test check_ip_location when not in GB."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"country": "US"}
        mock_get.return_value = mock_response
        
        is_gb, country = check_ip_location()
        
        assert is_gb is False
        assert country == "US"

    @patch("src.radio_curator.main.requests.get")
    def test_check_ip_location_error(self, mock_get):
        """Test check_ip_location on error."""
        mock_get.side_effect = Exception("Network error")
        
        is_gb, country = check_ip_location()
        
        assert is_gb is None
        assert country is None

    def test_format_playlist_for_lyrics(self):
        """Test format_playlist_for_lyrics."""
        tracks = [
            {'artist': 'Artist 1', 'title': 'Title 1'},
            {'artist': 'Artist 2', 'title': 'Title 2'}
        ]
        broadcast_date = "2023-01-01"
        
        result = format_playlist_for_lyrics("Show Title", tracks, broadcast_date)
        
        assert "BBC Playlist: Show Title" in result
        assert "Broadcast Date: 2023-01-01" in result
        assert "1. Artist 1 - Title 1" in result
        assert "2. Artist 2 - Title 2" in result

    @patch("src.radio_curator.main.glob.glob")
    def test_find_downloaded_audio_files(self, mock_glob):
        """Test find_downloaded_audio_files."""
        # Mock glob to return files for different extensions
        mock_glob.side_effect = [
            ["file.mp3"], # mp3
            [],           # m4a
            ["file.flac"],# flac
            []            # wav
        ]
        
        files = find_downloaded_audio_files("pid")
        
        assert len(files) == 2
        assert "file.mp3" in files
        assert "file.flac" in files

    @patch("src.radio_curator.main.shutil.move")
    @patch("src.radio_curator.main.os.makedirs")
    @patch("src.radio_curator.main.os.path.exists")
    def test_move_files_to_jellyfin(self, mock_exists, mock_makedirs, mock_move):
        """Test move_files_to_jellyfin."""
        mock_exists.return_value = False # Trigger makedirs
        audio_files = ["/source/file.mp3"]
        jellyfin_dir = "/dest"
        
        moved = move_files_to_jellyfin(audio_files, jellyfin_dir)
        
        mock_makedirs.assert_called_once_with(jellyfin_dir, exist_ok=True)
        mock_move.assert_called_once_with("/source/file.mp3", "/dest/file.mp3")
        assert moved == ["/dest/file.mp3"]

    @patch("src.radio_curator.main.requests.post")
    def test_trigger_jellyfin_rescan(self, mock_post):
        """Test trigger_jellyfin_rescan."""
        trigger_jellyfin_rescan("http://jellyfin", "token", "lib_id")
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://jellyfin/Items/lib_id/Refresh?Recursive=true"
        assert kwargs['headers'] == {"X-Emby-Token": "token"}

    @patch("src.radio_curator.main.check_ip_location")
    @patch("src.radio_curator.main.subprocess.run")
    @patch("src.radio_curator.main.parse_bbc_playlist")
    @patch("src.radio_curator.main.find_downloaded_audio_files")
    @patch("src.radio_curator.main.add_playlist_to_audio_metadata")
    def test_download_radio_show_success(
        self, mock_add_meta, mock_find_files, mock_parse, mock_run, mock_check_ip
    ):
        """Test download_radio_show success path."""
        mock_check_ip.return_value = (True, "GB")
        mock_parse.return_value = ("Title", [{"title": "T"}], "Date", "Desc")
        mock_find_files.return_value = ["file.mp3"]
        
        download_radio_show("pid")
        
        mock_run.assert_called_once()
        mock_parse.assert_called_once_with("pid")
        mock_add_meta.assert_called_once()

    @patch("src.radio_curator.main.check_ip_location")
    @patch("builtins.input", return_value="n")
    def test_download_radio_show_wrong_ip_cancel(self, mock_input, mock_check_ip):
        """Test download_radio_show cancellation on wrong IP."""
        mock_check_ip.return_value = (False, "US")
        
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            download_radio_show("pid")
            
        output = mock_stdout.getvalue()
        assert "Download cancelled" in output

    @patch("src.radio_curator.main.check_ip_location")
    @patch("src.radio_curator.main.subprocess.run")
    @patch("src.radio_curator.main.parse_bbc_playlist")
    @patch("src.radio_curator.main.find_downloaded_audio_files")
    @patch("src.radio_curator.main.move_files_to_jellyfin")
    @patch("src.radio_curator.main.trigger_jellyfin_rescan")
    @patch("src.radio_curator.main.add_playlist_to_audio_metadata")
    def test_download_radio_show_jellyfin(
        self, mock_add_meta, mock_trigger, mock_move, mock_find_files, mock_parse, mock_run, mock_check_ip
    ):
        """Test download_radio_show with Jellyfin integration."""
        mock_check_ip.return_value = (True, "GB")
        mock_parse.return_value = ("Title", [{"title": "T"}], "Date", "Desc")
        mock_find_files.return_value = ["file.mp3"]
        mock_move.return_value = ["/dest/file.mp3"]
        
        download_radio_show("pid", jellyfin_dir="/dest", jellyfin_url="http://url", jellyfin_token="token")
        
        mock_move.assert_called_once()
        mock_trigger.assert_called_once()

class TestMetadataFunctions:
    """Tests for metadata manipulation functions."""

    @patch("src.radio_curator.main.File")
    @patch("src.radio_curator.main.USLT")
    def test_add_playlist_to_audio_metadata_mp3(self, mock_uslt, mock_file):
        """Test adding metadata to MP3 file."""
        # Mock ID3 file
        mock_audio = MagicMock(spec=ID3)
        # Setup dictionary behavior for 'USLT::eng'
        mock_audio.__contains__.return_value = True
        mock_audio.__getitem__.return_value = MagicMock(text="Existing lyrics")
        
        mock_file.return_value = mock_audio
        
        result = add_playlist_to_audio_metadata("test.mp3", "New Playlist")
        
        assert result is True
        mock_file.assert_called_once_with("test.mp3")
        mock_audio.save.assert_called_once()
        # Check that USLT was instantiated with combined lyrics
        mock_uslt.assert_called_with(encoding=3, lang='eng', desc='', text="Existing lyrics\n\nNew Playlist")

    @patch("src.radio_curator.main.File")
    def test_add_playlist_to_audio_metadata_mp4(self, mock_file):
        """Test adding metadata to MP4/M4A file."""
        # Mock MP4 file
        mock_audio = MagicMock(spec=MP4)
        mock_audio.get.return_value = ["Existing lyrics"]
        
        mock_file.return_value = mock_audio
        
        result = add_playlist_to_audio_metadata("test.m4a", "New Playlist")
        
        assert result is True
        mock_audio.save.assert_called_once()
        # Verify assignment call instead of checking value via getitem
        mock_audio.__setitem__.assert_called_with('\xa9lyr', ["Existing lyrics\n\nNew Playlist"])

    @patch("src.radio_curator.main.File")
    def test_add_playlist_to_audio_metadata_flac(self, mock_file):
        """Test adding metadata to FLAC file."""
        # Mock FLAC file
        mock_audio = MagicMock(spec=FLAC)
        mock_audio.get.return_value = ["Existing lyrics"]
        
        mock_file.return_value = mock_audio
        
        result = add_playlist_to_audio_metadata("test.flac", "New Playlist")
        
        assert result is True
        mock_audio.save.assert_called_once()
        # Verify assignment call instead of checking value via getitem
        mock_audio.__setitem__.assert_called_with('LYRICS', ["Existing lyrics\n\nNew Playlist"])

    @patch("src.radio_curator.main.File")
    def test_add_playlist_to_audio_metadata_unsupported(self, mock_file):
        """Test adding metadata to unsupported file type."""
        mock_audio = MagicMock()
        # Not an instance of ID3, MP4, or FLAC
        mock_file.return_value = mock_audio
        
        result = add_playlist_to_audio_metadata("test.wav", "New Playlist")
        
        assert result is False

    @patch("src.radio_curator.main.File")
    def test_add_playlist_to_audio_metadata_error(self, mock_file):
        """Test error handling in add_playlist_to_audio_metadata."""
        mock_file.side_effect = Exception("File error")
        
        result = add_playlist_to_audio_metadata("test.mp3", "New Playlist")
        
        assert result is False
