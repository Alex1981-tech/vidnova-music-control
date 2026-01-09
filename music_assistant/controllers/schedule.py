"""MusicAssistant Schedule Controller.

Handles all logic for scheduled music playback, including:
- Time-based playback scheduling
- Player selection with volume settings
- Playlist/track selection
- Player grouping for synchronized playback
- Content looping within time intervals
- Scheduled announcements
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiofiles
import shortuuid
from music_assistant_models.config_entries import ConfigEntry, ConfigValueType
from music_assistant_models.enums import QueueOption, RepeatMode

from music_assistant.constants import (
    ANNOUNCEMENTS_DIR,
    DB_TABLE_SCHEDULES,
    SCHEDULE_CHECK_INTERVAL,
)
from music_assistant.helpers.api import api_command
from music_assistant.helpers.database import DatabaseConnection
from music_assistant.helpers.json import json_dumps, json_loads
from music_assistant.models.core_controller import CoreController
from music_assistant.models.schedule import (
    PlayerVolumeSetting,
    Schedule,
    ScheduledAnnouncement,
    ScheduleState,
)

if TYPE_CHECKING:
    from music_assistant_models.config_entries import CoreConfig

    from music_assistant import MusicAssistant

DB_SCHEMA_VERSION = 1


class ScheduleController(CoreController):
    """Controller for scheduled music playback."""

    domain: str = "schedule"

    def __init__(self, mass: MusicAssistant) -> None:
        """Initialize core controller."""
        super().__init__(mass)
        self.database: DatabaseConnection | None = None
        self._schedules: dict[str, Schedule] = {}
        self._active_schedules: set[str] = set()
        self._announcement_last_played: dict[str, dict[str, float]] = {}
        self._scheduler_task: asyncio.Task | None = None
        # Track sync groups created for schedules: schedule_id -> group_player_id
        self._schedule_groups: dict[str, str] = {}
        self.manifest.name = "Schedule controller"
        self.manifest.description = (
            "Music Assistant's core controller for scheduled music playback."
        )
        self.manifest.icon = "calendar-clock"

    async def get_config_entries(
        self,
        action: str | None = None,
        values: dict[str, ConfigValueType] | None = None,
    ) -> tuple[ConfigEntry, ...]:
        """Return all Config Entries for this core module (if any)."""
        return ()

    async def setup(self, config: CoreConfig) -> None:
        """Async initialize of schedule module."""
        self.logger.info("Initializing schedule controller...")
        await self._setup_database()
        await self._setup_announcements_dir()
        await self._load_schedules()
        self._start_scheduler()

    async def close(self) -> None:
        """Cleanup on exit."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
        if self.database:
            await self.database.close()

    # ========== API Commands ==========

    @api_command("schedule/all")
    def get_all(self) -> list[Schedule]:
        """Return all schedules."""
        return list(self._schedules.values())

    @api_command("schedule/get")
    def get(self, schedule_id: str) -> Schedule | None:
        """Return schedule by ID."""
        return self._schedules.get(schedule_id)

    @api_command("schedule/create")
    async def create(
        self,
        name: str,
        start_time: str,
        end_time: str,
        days_of_week: list[int],
        media_items: list[str],
        players: list[dict[str, Any]],
        enabled: bool = True,
        group_players: bool = False,
        loop_content: bool = True,
        shuffle: bool = False,
        announcements: list[dict[str, Any]] | None = None,
    ) -> Schedule:
        """Create a new schedule.

        :param name: Name of the schedule.
        :param start_time: Start time in HH:MM format.
        :param end_time: End time in HH:MM format.
        :param days_of_week: List of days (0=Mon, 6=Sun).
        :param media_items: List of media URIs to play.
        :param players: List of player settings with player_id and volume.
        :param enabled: Whether the schedule is enabled.
        :param group_players: Whether to group players for sync playback.
        :param loop_content: Whether to loop content.
        :param shuffle: Whether to shuffle playback.
        :param announcements: List of announcement configurations.
        """
        schedule_id = shortuuid.random(8)
        current_time = int(time.time())

        # Parse player settings
        player_settings = [
            PlayerVolumeSetting(
                player_id=p["player_id"],
                volume=p.get("volume", 50),
            )
            for p in players
        ]

        # Parse announcements
        announcement_list: list[ScheduledAnnouncement] = []
        if announcements:
            for ann in announcements:
                announcement_list.append(
                    ScheduledAnnouncement(
                        announcement_id=ann.get("announcement_id", shortuuid.random(8)),
                        name=ann["name"],
                        file_path=ann["file_path"],
                        time=ann["time"],
                        repeat_interval=ann.get("repeat_interval"),
                    )
                )

        schedule = Schedule(
            schedule_id=schedule_id,
            name=name,
            enabled=enabled,
            start_time=start_time,
            end_time=end_time,
            days_of_week=days_of_week,
            media_items=media_items,
            players=player_settings,
            group_players=group_players,
            loop_content=loop_content,
            shuffle=shuffle,
            announcements=announcement_list,
            created_at=current_time,
            updated_at=current_time,
        )

        await self._save_schedule(schedule)
        self._schedules[schedule_id] = schedule
        self._emit_schedule_event("ADDED", schedule)
        self.logger.info("Created schedule: %s (%s)", name, schedule_id)
        return schedule

    @api_command("schedule/update")
    async def update(
        self,
        schedule_id: str,
        name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        days_of_week: list[int] | None = None,
        media_items: list[str] | None = None,
        players: list[dict[str, Any]] | None = None,
        enabled: bool | None = None,
        group_players: bool | None = None,
        loop_content: bool | None = None,
        shuffle: bool | None = None,
        announcements: list[dict[str, Any]] | None = None,
    ) -> Schedule:
        """Update an existing schedule.

        :param schedule_id: ID of the schedule to update.
        :param name: New name (optional).
        :param start_time: New start time (optional).
        :param end_time: New end time (optional).
        :param days_of_week: New days of week (optional).
        :param media_items: New media items (optional).
        :param players: New player settings (optional).
        :param enabled: New enabled state (optional).
        :param group_players: New group players setting (optional).
        :param loop_content: New loop content setting (optional).
        :param shuffle: New shuffle setting (optional).
        :param announcements: New announcements (optional).
        """
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            msg = f"Schedule not found: {schedule_id}"
            raise ValueError(msg)

        if name is not None:
            schedule.name = name
        if start_time is not None:
            schedule.start_time = start_time
        if end_time is not None:
            schedule.end_time = end_time
        if days_of_week is not None:
            schedule.days_of_week = days_of_week
        if media_items is not None:
            schedule.media_items = media_items
        if players is not None:
            schedule.players = [
                PlayerVolumeSetting(
                    player_id=p["player_id"],
                    volume=p.get("volume", 50),
                )
                for p in players
            ]
        if enabled is not None:
            schedule.enabled = enabled
        if group_players is not None:
            schedule.group_players = group_players
        if loop_content is not None:
            schedule.loop_content = loop_content
        if shuffle is not None:
            schedule.shuffle = shuffle
        if announcements is not None:
            schedule.announcements = [
                ScheduledAnnouncement(
                    announcement_id=ann.get("announcement_id", shortuuid.random(8)),
                    name=ann["name"],
                    file_path=ann["file_path"],
                    time=ann["time"],
                    repeat_interval=ann.get("repeat_interval"),
                )
                for ann in announcements
            ]

        schedule.updated_at = int(time.time())
        await self._save_schedule(schedule)
        self._emit_schedule_event("UPDATED", schedule)
        self.logger.info("Updated schedule: %s (%s)", schedule.name, schedule_id)
        return schedule

    @api_command("schedule/delete")
    async def delete(self, schedule_id: str) -> None:
        """Delete a schedule.

        :param schedule_id: ID of the schedule to delete.
        """
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            msg = f"Schedule not found: {schedule_id}"
            raise ValueError(msg)

        # Stop if active
        if schedule_id in self._active_schedules:
            await self._stop_schedule(schedule)

        # Delete from database
        assert self.database is not None
        await self.database.delete(DB_TABLE_SCHEDULES, {"schedule_id": schedule_id})

        # Remove from memory
        del self._schedules[schedule_id]
        self._emit_schedule_event("REMOVED", schedule)
        self.logger.info("Deleted schedule: %s (%s)", schedule.name, schedule_id)

    @api_command("schedule/enable")
    async def set_enabled(self, schedule_id: str, enabled: bool) -> Schedule:
        """Enable or disable a schedule.

        :param schedule_id: ID of the schedule.
        :param enabled: Whether to enable or disable.
        """
        return await self.update(schedule_id, enabled=enabled)

    @api_command("schedule/trigger")
    async def trigger(self, schedule_id: str) -> None:
        """Manually trigger a schedule to start.

        :param schedule_id: ID of the schedule to trigger.
        """
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            msg = f"Schedule not found: {schedule_id}"
            raise ValueError(msg)

        if schedule_id in self._active_schedules:
            self.logger.warning("Schedule already active: %s", schedule_id)
            return

        await self._start_schedule(schedule)

    @api_command("schedule/stop")
    async def stop(self, schedule_id: str) -> None:
        """Stop an active schedule.

        :param schedule_id: ID of the schedule to stop.
        """
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            msg = f"Schedule not found: {schedule_id}"
            raise ValueError(msg)

        if schedule_id not in self._active_schedules:
            self.logger.warning("Schedule not active: %s", schedule_id)
            return

        await self._stop_schedule(schedule)

    @api_command("schedule/upload_announcement")
    async def upload_announcement(
        self,
        name: str,
        file_data: str,
        file_name: str,
    ) -> ScheduledAnnouncement:
        """Upload an audio file for announcements.

        :param name: Display name for the announcement.
        :param file_data: Base64 encoded audio file data.
        :param file_name: Original file name.
        """
        announcement_id = shortuuid.random(8)
        safe_filename = f"{announcement_id}_{file_name}"
        file_path = os.path.join(self._announcements_path, safe_filename)

        # Decode and save file
        file_bytes = base64.b64decode(file_data)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)

        self.logger.info("Uploaded announcement file: %s", safe_filename)

        return ScheduledAnnouncement(
            announcement_id=announcement_id,
            name=name,
            file_path=file_path,
            time="",
            repeat_interval=None,
        )

    @api_command("schedule/delete_announcement")
    async def delete_announcement_file(self, file_path: str) -> None:
        """Delete an announcement audio file.

        :param file_path: Path to the file to delete.
        """
        # Security check - ensure file is in announcements directory
        if not file_path.startswith(self._announcements_path):
            msg = "Invalid file path"
            raise ValueError(msg)

        if os.path.exists(file_path):
            os.remove(file_path)
            self.logger.info("Deleted announcement file: %s", file_path)

    @api_command("schedule/list_announcements")
    def list_announcement_files(self) -> list[dict[str, str]]:
        """List all uploaded announcement files."""
        files = []
        if os.path.exists(self._announcements_path):
            for filename in os.listdir(self._announcements_path):
                file_path = os.path.join(self._announcements_path, filename)
                if os.path.isfile(file_path):
                    files.append({"name": filename, "path": file_path})
        return files

    # ========== Private Methods ==========

    @property
    def _announcements_path(self) -> str:
        """Return the path to announcements directory."""
        return os.path.join(self.mass.storage_path, ANNOUNCEMENTS_DIR)

    async def _setup_database(self) -> None:
        """Initialize database."""
        db_path = os.path.join(self.mass.storage_path, "schedule.db")
        self.database = DatabaseConnection(db_path)
        await self.database.setup()
        await self._create_database_tables()

    async def _create_database_tables(self) -> None:
        """Create database table(s)."""
        assert self.database is not None
        await self.database.execute(
            f"""CREATE TABLE IF NOT EXISTS {DB_TABLE_SCHEDULES}(
                schedule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                days_of_week TEXT NOT NULL,
                media_items TEXT NOT NULL,
                players TEXT NOT NULL,
                group_players INTEGER DEFAULT 0,
                loop_content INTEGER DEFAULT 1,
                shuffle INTEGER DEFAULT 0,
                announcements TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )"""
        )
        await self.database.commit()

    async def _setup_announcements_dir(self) -> None:
        """Create announcements directory if not exists."""
        os.makedirs(self._announcements_path, exist_ok=True)

    async def _load_schedules(self) -> None:
        """Load all schedules from database."""
        assert self.database is not None
        rows = await self.database.get_rows(DB_TABLE_SCHEDULES, limit=1000)
        for row in rows:
            schedule = self._schedule_from_db_row(dict(row))
            self._schedules[schedule.schedule_id] = schedule
        self.logger.info("Loaded %d schedules from database", len(self._schedules))

    async def _save_schedule(self, schedule: Schedule) -> None:
        """Save schedule to database."""
        assert self.database is not None
        await self.database.insert_or_replace(
            DB_TABLE_SCHEDULES,
            {
                "schedule_id": schedule.schedule_id,
                "name": schedule.name,
                "enabled": 1 if schedule.enabled else 0,
                "start_time": schedule.start_time,
                "end_time": schedule.end_time,
                "days_of_week": json_dumps(schedule.days_of_week),
                "media_items": json_dumps(schedule.media_items),
                "players": json_dumps([p.to_dict() for p in schedule.players]),
                "group_players": 1 if schedule.group_players else 0,
                "loop_content": 1 if schedule.loop_content else 0,
                "shuffle": 1 if schedule.shuffle else 0,
                "announcements": json_dumps([a.to_dict() for a in schedule.announcements]),
                "created_at": schedule.created_at,
                "updated_at": schedule.updated_at,
            },
        )

    def _schedule_from_db_row(self, row: dict[str, Any]) -> Schedule:
        """Create Schedule object from database row."""
        players_data = json_loads(row["players"])
        announcements_data = json_loads(row["announcements"] or "[]")

        return Schedule(
            schedule_id=row["schedule_id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
            days_of_week=json_loads(row["days_of_week"]),
            media_items=json_loads(row["media_items"]),
            players=[PlayerVolumeSetting.from_dict(p) for p in players_data],
            group_players=bool(row["group_players"]),
            loop_content=bool(row["loop_content"]),
            shuffle=bool(row["shuffle"]),
            announcements=[ScheduledAnnouncement.from_dict(a) for a in announcements_data],
            created_at=row["created_at"] or 0,
            updated_at=row["updated_at"] or 0,
        )

    def _start_scheduler(self) -> None:
        """Start the scheduler loop."""
        self._scheduler_task = self.mass.create_task(self._scheduler_loop())

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks schedules periodically."""
        # Wait for players to be registered before starting the scheduler
        # This is important because player providers (like LinkPlay) need time
        # to discover and register their devices
        self.logger.info("Scheduler waiting 60 seconds for player registration...")
        await asyncio.sleep(60)
        self.logger.info("Scheduler starting checks...")
        while not self.mass.closing:
            try:
                await self._check_schedules()
            except Exception as exc:
                self.logger.exception("Error in scheduler loop: %s", exc)
            await asyncio.sleep(SCHEDULE_CHECK_INTERVAL)

    async def _check_schedules(self) -> None:
        """Check all schedules and start/stop as needed."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday, 6=Sunday

        for schedule in self._schedules.values():
            if not schedule.enabled:
                continue

            should_be_active = self._should_be_active(schedule, current_time, current_day)
            is_active = schedule.schedule_id in self._active_schedules

            if should_be_active and not is_active:
                await self._start_schedule(schedule)
            elif not should_be_active and is_active:
                await self._stop_schedule(schedule)
            elif is_active:
                # Check announcements
                await self._check_announcements(schedule, now)

    def _should_be_active(
        self, schedule: Schedule, current_time: str, current_day: int
    ) -> bool:
        """Check if schedule should be active at current time."""
        if current_day not in schedule.days_of_week:
            return False

        start = schedule.start_time
        end = schedule.end_time

        # Handle overnight schedules (e.g., 22:00 - 06:00)
        if start > end:
            return current_time >= start or current_time < end
        else:
            return start <= current_time < end

    async def _start_schedule(self, schedule: Schedule) -> None:
        """Start a schedule - begin playback on configured players."""
        self.logger.info("Starting schedule: %s", schedule.name)

        if not schedule.players:
            self.logger.warning("Schedule has no players configured: %s", schedule.schedule_id)
            return

        if not schedule.media_items:
            self.logger.warning("Schedule has no media items configured: %s", schedule.schedule_id)
            return

        try:
            # Set volume for each player
            for player_setting in schedule.players:
                try:
                    await self.mass.players.cmd_volume_set(
                        player_setting.player_id,
                        player_setting.volume,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "Failed to set volume for player %s: %s",
                        player_setting.player_id,
                        exc,
                    )

            # Get all player IDs
            all_player_ids = [p.player_id for p in schedule.players]
            target_player_id = all_player_ids[0]

            # If grouping is enabled and we have multiple players, create a sync group
            if schedule.group_players and len(schedule.players) > 1:
                # Check if we already have a group for this schedule
                existing_group_id = self._schedule_groups.get(schedule.schedule_id)
                if existing_group_id:
                    # Remove old group first
                    try:
                        await self.mass.players.remove_group_player(existing_group_id)
                        self.logger.info("Removed old schedule group: %s", existing_group_id)
                    except Exception as exc:
                        self.logger.debug("Could not remove old group %s: %s", existing_group_id, exc)

                # Determine provider from first player
                first_player = self.mass.players.get(target_player_id)
                if not first_player:
                    self.logger.error("First player %s not found", target_player_id)
                    return

                provider_id = first_player.provider.instance_id

                # Create new sync group named after the schedule
                group_name = f"Schedule: {schedule.name}"
                try:
                    group_player = await self.mass.players.create_group_player(
                        provider=provider_id,
                        name=group_name,
                        members=all_player_ids,
                        dynamic=True,
                    )
                    target_player_id = group_player.player_id
                    self._schedule_groups[schedule.schedule_id] = target_player_id
                    self.logger.info(
                        "Created schedule sync group '%s' with ID %s for players: %s",
                        group_name,
                        target_player_id,
                        all_player_ids,
                    )
                    # Give time for group to initialize
                    await asyncio.sleep(2)
                except Exception as exc:
                    self.logger.warning(
                        "Failed to create sync group for schedule, falling back to first player: %s",
                        exc,
                    )
                    target_player_id = all_player_ids[0]

            # Configure repeat mode if looping
            if schedule.loop_content:
                self.mass.player_queues.set_repeat(target_player_id, RepeatMode.ALL)

            # Configure shuffle
            if schedule.shuffle:
                await self.mass.player_queues.set_shuffle(target_player_id, True)

            # Start playback
            self.logger.info("Starting playback on %s", target_player_id)
            await self.mass.player_queues.play_media(
                queue_id=target_player_id,
                media=schedule.media_items,
                option=QueueOption.REPLACE,
            )

            # Mark as active
            self._active_schedules.add(schedule.schedule_id)
            schedule.state = ScheduleState.PLAYING
            self._announcement_last_played[schedule.schedule_id] = {}
            self._emit_schedule_event("UPDATED", schedule)

        except Exception as exc:
            self.logger.exception("Failed to start schedule %s: %s", schedule.schedule_id, exc)

    async def _stop_schedule(self, schedule: Schedule) -> None:
        """Stop a schedule - stop playback on configured players."""
        self.logger.info("Stopping schedule: %s", schedule.name)

        try:
            # Check if we have a sync group for this schedule
            group_player_id = self._schedule_groups.get(schedule.schedule_id)
            if group_player_id:
                # Stop the group player first
                try:
                    await self.mass.players.cmd_stop(group_player_id)
                except Exception as exc:
                    self.logger.warning("Failed to stop group player %s: %s", group_player_id, exc)

                # Remove the sync group
                try:
                    await self.mass.players.remove_group_player(group_player_id)
                    self.logger.info(
                        "Removed schedule sync group: %s (schedule: %s)",
                        group_player_id,
                        schedule.name,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "Failed to remove schedule group %s: %s",
                        group_player_id,
                        exc,
                    )
                finally:
                    # Clean up tracking dict
                    self._schedule_groups.pop(schedule.schedule_id, None)
            else:
                # No group - stop individual players
                for player_setting in schedule.players:
                    try:
                        await self.mass.players.cmd_stop(player_setting.player_id)
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to stop player %s: %s",
                            player_setting.player_id,
                            exc,
                        )

        except Exception as exc:
            self.logger.exception("Failed to stop schedule %s: %s", schedule.schedule_id, exc)
        finally:
            # Mark as inactive
            self._active_schedules.discard(schedule.schedule_id)
            schedule.state = ScheduleState.IDLE
            self._announcement_last_played.pop(schedule.schedule_id, None)
            self._emit_schedule_event("UPDATED", schedule)

    async def _check_announcements(self, schedule: Schedule, now: datetime) -> None:
        """Check and play scheduled announcements."""
        current_time = now.strftime("%H:%M")
        current_timestamp = now.timestamp()

        for announcement in schedule.announcements:
            should_play = False

            # Check if it's time to play
            if announcement.time == current_time:
                last_played = self._announcement_last_played.get(
                    schedule.schedule_id, {}
                ).get(announcement.announcement_id, 0)

                # Check repeat interval
                if announcement.repeat_interval:
                    min_interval = announcement.repeat_interval * 60  # Convert to seconds
                    if current_timestamp - last_played >= min_interval:
                        should_play = True
                else:
                    # One-time announcement - check if played in last minute
                    if current_timestamp - last_played > 60:
                        should_play = True

            if should_play:
                await self._play_announcement(schedule, announcement)
                if schedule.schedule_id not in self._announcement_last_played:
                    self._announcement_last_played[schedule.schedule_id] = {}
                self._announcement_last_played[schedule.schedule_id][
                    announcement.announcement_id
                ] = current_timestamp

    async def _play_announcement(
        self, schedule: Schedule, announcement: ScheduledAnnouncement
    ) -> None:
        """Play an announcement on all schedule players."""
        self.logger.info(
            "Playing announcement '%s' for schedule '%s'",
            announcement.name,
            schedule.name,
        )

        # Build URL for the announcement file
        announcement_url = (
            f"file://{announcement.file_path}"
            if announcement.file_path.startswith("/")
            else announcement.file_path
        )

        for player_setting in schedule.players:
            try:
                await self.mass.players.play_announcement(
                    player_id=player_setting.player_id,
                    url=announcement_url,
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to play announcement on player %s: %s",
                    player_setting.player_id,
                    exc,
                )

    def _emit_schedule_event(self, event_type: str, schedule: Schedule) -> None:
        """Emit a schedule-related event (logging only for now)."""
        # EventType enum doesn't have schedule-specific events yet
        # Just log for now instead of signaling
        self.logger.debug(
            "Schedule event: %s for %s (%s)",
            event_type,
            schedule.name,
            schedule.schedule_id,
        )
