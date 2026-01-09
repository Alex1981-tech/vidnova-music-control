"""Data models for Schedule functionality."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from mashumaro import DataClassDictMixin


class ScheduleState(StrEnum):
    """Schedule execution state."""

    IDLE = "idle"  # Not currently active
    PLAYING = "playing"  # Currently playing scheduled content
    PAUSED = "paused"  # Paused by user during scheduled time


@dataclass
class PlayerVolumeSetting(DataClassDictMixin):
    """Volume setting for a specific player in a schedule."""

    player_id: str
    volume: int  # 0-100


@dataclass
class ScheduledAnnouncement(DataClassDictMixin):
    """Announcement configuration within a schedule."""

    announcement_id: str
    name: str
    file_path: str
    time: str  # HH:MM format
    repeat_interval: int | None = None  # minutes, None = one-time only


@dataclass
class Schedule(DataClassDictMixin):
    """Schedule configuration for automated playback."""

    schedule_id: str
    name: str
    enabled: bool = True
    start_time: str = ""  # HH:MM format
    end_time: str = ""  # HH:MM format
    days_of_week: list[int] = field(default_factory=list)  # 0=Mon, 6=Sun
    media_items: list[str] = field(default_factory=list)  # URIs of playlists/tracks
    players: list[PlayerVolumeSetting] = field(default_factory=list)
    group_players: bool = False  # Group players for synchronized playback
    loop_content: bool = True  # Loop media within time interval
    shuffle: bool = False  # Shuffle playback order
    announcements: list[ScheduledAnnouncement] = field(default_factory=list)
    created_at: int = 0  # Unix timestamp
    updated_at: int = 0  # Unix timestamp

    # Runtime state (not persisted)
    state: ScheduleState = ScheduleState.IDLE
