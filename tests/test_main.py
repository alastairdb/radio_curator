"""Tests for main entry point."""

from unittest.mock import patch
import sys
from io import StringIO
from src.radio_curator.main import main as main_entry

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
        assert 'Usage: python -m radio_curator <command>' in output
        assert 'Available commands: ytmusic-api, bbc-playlist' in output

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
        # Capture stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        # Test with unknown command
        sys.argv = ['radio_curator', 'unknown-command']
        main_entry()
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert 'Unknown command: unknown-command' in output
        assert 'Available commands: ytmusic-api, bbc-playlist' in output
