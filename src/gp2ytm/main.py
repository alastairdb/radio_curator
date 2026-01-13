"""Main entry point for the GP2YTM application."""

import sys

from .ytmusic_api import main as ytmusic_api_main
from .bbc_playlist_to_ytmusic import main as bbc_playlist_main

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m gp2ytm <command>")
        print("Available commands: ytmusic-api, bbc-playlist")
        return
    
    command = sys.argv[1]
    
    if command == "ytmusic-api":
        # Remove the command from argv and pass the rest to the module
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        ytmusic_api_main()
    elif command == "bbc-playlist":
        # Remove the command from argv and pass the rest to the module
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        bbc_playlist_main()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: ytmusic-api, bbc-playlist")

if __name__ == "__main__":
    main()
