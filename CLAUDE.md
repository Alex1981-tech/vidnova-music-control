# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
This guidance is aimed at Claude Code but may as well be suitable for other AI tooling, such as Github CoPilot.

Instructions for an LLM (such as Claude) working with the code:

- Take these instructions in mind
- Look at existing provider implementations, type hints, docstrings and comments
- Propose changes to extend this document with new learnings.


## Project Overview

Music Assistant is a (async) Python 3 based music library manager that connects to streaming services and supports various connected speakers. It's designed to run as a server on always-on devices and integrates with Home Assistant.

## Development Commands

### Setup and Dependencies
- `scripts/setup.sh` - Initial development setup (creates venv, installs dependencies, configures pre-commit)
- Always re-run after pulling latest code as requirements may change

### Testing and Quality
- `pytest` - Run all tests
- `pytest tests/specific_test.py` - Run a specific test file
- `pytest --cov music_assistant` - Run tests with coverage (configured in pyproject.toml)
- `pre-commit run --all-files` - Run all pre-commit hooks

Always run `pre-commit run --all-files` after a code change to ensure the new code adheres to the project standards.

### Running the Server
- Use F5 in VS Code to start Music Assistant locally (debug mode)
- Or run from command line: `python -m music_assistant --log-level debug`
- Server runs on `localhost:8095`
- Entry point: `music_assistant.__main__:main`

## Architecture

### Core Components

1. **MusicAssistant (`music_assistant/mass.py`)** - Main orchestrator class
2. **Controllers (`music_assistant/controllers/`)** - Core functionality modules:
   - `music.py` - Music library management and provider orchestration
   - `players.py` - Player management and control
   - `player_queues.py` - Playback queue management
   - `streams.py` - Audio streaming logic
   - `webserver.py` - Web API server
   - `config.py` - Configuration management
   - `cache.py` - Caching layer
   - `metadata.py` - Metadata handling

3. **Models (`music_assistant/models/`)** - Base classes and interfaces:
   - `core_controller.py` - Base class/model for all core controllers
   - `music_provider.py` - Base for music providers
   - `player.py` - Base for players (provided by player providers)
   - `player_provider.py` - Base for player providers
   - `plugin.py` - Plugin system base

4. **Providers (`music_assistant/providers/`)** - External service integrations:
   - Music providers (Spotify, Apple Music, Tidal, etc.)
   - Player providers (Sonos, Chromecast, AirPlay, etc.)
   - Metadata providers (MusicBrainz, TheAudioDB, etc.)
   - Plugin providers for additional functionality (such as spotify connect or lastfm scrobbling)

5. **Helpers (`music_assistant/helpers/`)** - Utility modules for common tasks

### Provider Architecture

Providers are modular components that extend Music Assistant's capabilities:

- **Music Providers**: Add music sources (streaming services, local files)
- **Player Providers**: Add playback targets (speakers, media players)
- **Metadata Providers**: Add metadata sources (cover art, lyrics, etc.)
- **Plugin Providers**: Add additional functionality

Each provider has (at least):
- `__init__.py` - Main provider logic
- `manifest.json` - Provider metadata and configuration schema
- many providers choose to split up the code into several smaller files for readability and maintenance.

Template providers are available in `_demo_*_provider` directories.
These demo/example implementations have a lot of docstrings and comments to help you setup a new provider.

### Data Flow

1. **Music Library**: Controllers sync data from music providers to internal database
2. **Playback**: Stream controllers handle audio streaming to player providers
3. **Queue Management**: Player queues manage playback state and track progression
4. **Web API**: Webserver controller exposes REST API for frontend communication

## Key Configuration

- **Python**: 3.12+ required
- **Dependencies**: Defined in `pyproject.toml`
- **Database**: SQLite via aiosqlite
- **Async**: Heavy use of asyncio throughout codebase
- **External Dependencies**: ffmpeg (v6.1+), various provider-specific binaries

## Development Notes

- Uses ruff for linting/formatting (config in pyproject.toml)
- Type checking with mypy (strict configuration)
- Pre-commit hooks for code quality
- Test framework: pytest with async support
- Docker-based deployment (not standalone pip package)
- VS Code launch configurations provided for debugging

## Code Style Guidelines

### Docstring Format

Music Assistant uses **Sphinx-style docstrings** with `:param:` syntax for documenting function parameters. This is the standard format used throughout the codebase.

**Correct format:**
```python
def my_function(param1: str, param2: int, param3: bool = False) -> str:
    """Brief one-line description of the function.

    Optional longer description providing more context about what the function does,
    why it exists, and any important implementation details.

    :param param1: Description of what param1 is used for.
    :param param2: Description of what param2 is used for.
    :param param3: Description of what param3 is used for.
    """
```

**Key points:**
- Use `:param param_name: description` format for all parameters
- Brief summary on first line, followed by blank line
- Optional detailed description before parameters section
- No need to document types in docstring (use type hints instead)
- No need to document return types in docstring (use type hints instead)

**Incorrect formats to avoid:**
```python
# ❌ Bullet-style (being phased out)
"""Function description.

- param1: Description
- param2: Description
"""

# ❌ Google-style
"""Function description.

Args:
    param1: Description
    param2: Description
"""
```

**For simple functions**, a single-line docstring is acceptable:
```python
def get_item(self, item_id: str) -> Item:
    """Get an item by its ID."""
```

**Enforcement:**
- Ruff with pydocstyle rules enforces basic docstring structure
- Pre-commit hooks check docstring format
- The API documentation generator parses Sphinx-style docstrings for the web interface

## Branching Strategy

### Branch Structure
- **`dev`** - Primary development branch, all PRs target this branch
- **`stable`** - Stable release branch for production releases

### Release Process
- **Beta releases**: Released from `dev` branch on-demand when new features are stable
- **Stable releases**: Released from `stable` branch on-demand
- **Patch releases**: Cherry-picked from `dev` to `stable` (bugfixes only)

### Versioning
- **Beta versions**: Next minor version + beta number (e.g., `2.6.0b1`, `2.6.0b2`)
- **Stable versions**: Standard semantic versioning (e.g., `2.5.5`)
- **Patch versions**: Increment patch number (e.g., `2.5.5` → `2.5.6`)

### PR Workflow
1. Contributors create PRs against `dev`
2. PRs are labeled with type: `bugfix`, `maintenance`, `new feature`, etc.
3. PRs with `backport-to-stable` label are automatically backported to `stable`

### Backport Criteria
- **`backport-to-stable`**: Only for `bugfix` PRs that fix bugs also present in `stable`
- **`bugfix`**: General bugfix label (may be for dev-only features)
- Automated backport workflow creates patch release PRs to `stable`

## Testing

- Tests located in `tests/` directory
- Fixtures for test data in `tests/fixtures/`
- Provider-specific tests in `tests/providers/`
- Uses pytest-aiohttp for async web testing
- Syrupy for snapshot testing

## WebSocket API

The server uses WebSocket for client communication (not REST). Key points:

- WebSocket endpoint: `ws://localhost:8095/ws`
- Commands use `@api_command("command/path")` decorator
- Authentication required via `auth/login` then `auth` with token
- Frontend primarily uses `player_queues/all` for player selection (14 uses vs 1 for `players/all`)

Example API flow:
```python
# 1. Login
{"command": "auth/login", "message_id": "1", "args": {"username": "...", "password": "..."}}
# Returns: {"result": {"success": true, "access_token": "..."}}

# 2. Authenticate session
{"command": "auth", "message_id": "2", "args": {"token": "..."}}

# 3. Call API commands
{"command": "players/all", "message_id": "3"}
```

## Configuration System

- Settings stored in `data/settings.json`
- `ConfigController` uses delayed saving (`DEFAULT_SAVE_DELAY = 5` seconds)
- For immediate persistence, use `save(immediate=True)`
- Player configs created via `create_default_player_config()`

### Player Registration Flow

1. Provider discovers device
2. Calls `mass.players.register(player)`
3. `create_default_player_config()` creates config in settings
4. `on_player_register()` creates PlayerQueue
5. Player appears in API and frontend

### Important: Player Lifecycle

- Use `unregister(player_id, permanent=False)` to keep config on shutdown
- Use `remove(player_id)` only when permanently removing player (deletes config)
- User's `player_filter` preference can hide players in frontend even if API returns them

## Player Provider Implementation

When implementing a new player provider:

1. Inherit from `PlayerProvider` base class
2. Implement required methods: `async_setup()`, `async_on_start()`, `async_on_stop()`
3. Register players via `self.mass.players.register()`
4. Handle player state updates via `player.update_state()`
5. Use `unregister(permanent=False)` in cleanup to preserve configs across restarts

## Network Requirements

### Required Ports

Music Assistant uses several TCP ports that must be accessible:

| Port | Service | Description |
|------|---------|-------------|
| 8095 | WebSocket API | Main client communication endpoint |
| 8097 | Stream Server | Audio streaming to players (critical for playback) |
| 8927 | Alternative port | Additional streaming port |

**Important**: If using a firewall (UFW, iptables), ensure these ports are open:
```bash
sudo ufw allow 8095/tcp  # WebSocket API
sudo ufw allow 8097/tcp  # Stream server (required for audio playback!)
sudo ufw allow 8927/tcp  # Alternative streaming port
```

### Stream Server Configuration

The stream server (`music_assistant/controllers/streams/`) sends URLs to players for audio streaming.

Key settings in `Settings → Core modules → Streamserver`:
- **`publish_ip`**: IP address communicated to players. Must be reachable from players' network.
- **`bind_port`**: TCP port for stream server (default: 8097)
- **`bind_ip`**: Interface to bind to (default: 0.0.0.0 for all interfaces)

### Multi-Subnet Deployments

When server and players are on different subnets (e.g., server on 172.16.x.x, players on 192.168.x.x):

1. Ensure routing exists between subnets
2. **Open firewall ports** on the server - this is the most common issue!
3. If players can't reach the server's IP, configure `publish_ip` to an accessible address
4. Check player logs for `'status': 'load'` stuck state - indicates players can't fetch the stream URL

### Troubleshooting Playback Issues

**Symptom**: Players appear in UI but playback doesn't start (stuck in "loading")

**Diagnosis**:
1. Check server logs: `tail -f data/musicassistant.log | grep -i linkplay`
2. Look for player status: `'status': 'load'` (stuck) vs `'status': 'play'` (working)
3. Check if stream URL is reachable from player's network

**Common causes**:
- Firewall blocking port 8097 (most common!)
- `publish_ip` set to IP unreachable from players
- Network routing issues between subnets

**Solution**:
```bash
# Check if ports are open
ss -tlnp | grep -E "8095|8097"

# Open ports in UFW
sudo ufw allow 8097/tcp

# Verify connectivity from player subnet (if possible)
curl -I http://<server_ip>:8097/
```
