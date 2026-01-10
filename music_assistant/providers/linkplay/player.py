"""LinkPlay Player implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
from music_assistant_models.enums import PlayerFeature, PlaybackState, PlayerType
from music_assistant_models.player import DeviceInfo

from music_assistant.constants import (
    CONF_ENTRY_HTTP_PROFILE_DEFAULT_3,
)
from music_assistant.models.player import Player, PlayerMedia

from .constants import LINKPLAY_DEFAULT_PORT, LINKPLAY_TIMEOUT

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigEntry, ConfigValueType, PlayerConfig

    from .provider import LinkPlayProvider


class LinkPlayPlayer(Player):
    """Representation of a LinkPlay Player."""

    def __init__(
        self,
        provider: LinkPlayProvider,
        player_id: str,
        ip_address: str,
        device_info: dict,
    ) -> None:
        """Initialize LinkPlay Player."""
        super().__init__(provider, player_id)
        self.ip_address = ip_address
        self._linkplay_device_info = device_info
        self._last_status = {}
        self._play_start_time: float = 0  # Track when play was started

        # Set player attributes
        self._attr_type = PlayerType.PLAYER
        self._attr_name = device_info.get("name", f"LinkPlay {ip_address}")
        self._attr_available = True  # Start as available
        self._attr_powered = True  # Player is powered on
        self._attr_playback_state = PlaybackState.IDLE  # Initial state
        self._attr_supported_features = {
            PlayerFeature.POWER,
            PlayerFeature.PAUSE,
            PlayerFeature.VOLUME_SET,
            PlayerFeature.VOLUME_MUTE,
            PlayerFeature.PLAY_ANNOUNCEMENT,
            PlayerFeature.SET_MEMBERS,
        }
        self._attr_device_info = DeviceInfo(
            model=device_info.get("model", "LinkPlay Device"),
            manufacturer="LinkPlay",
            ip_address=ip_address,
        )
        # Enable polling to update player state
        self._attr_needs_poll = True
        self._attr_poll_interval = 5  # Poll every 5 seconds
        # Set initial volume level
        self._attr_volume_level = 50

    async def get_config_entries(
        self,
        action: str | None = None,
        values: dict[str, ConfigValueType] | None = None,
    ) -> list[ConfigEntry]:
        """Return all (provider/player specific) Config Entries for the player.

        LinkPlay devices need forced_content_length HTTP profile to work properly.
        """
        return [
            *await super().get_config_entries(action=action, values=values),
            CONF_ENTRY_HTTP_PROFILE_DEFAULT_3,
        ]

    async def power(self, powered: bool) -> None:
        """Send POWER command to player."""
        command = "PLAY" if powered else "PAUSE"
        await self._send_command(command)
        self._attr_playback_state = PlaybackState.PLAYING if powered else PlaybackState.PAUSED
        self._attr_powered = powered
        self.update_state()

    async def volume_set(self, volume_level: int) -> None:
        """Send VOLUME_SET command to player."""
        await self._send_command(f"setPlayerCmd:vol:{volume_level}")
        self._attr_volume_level = volume_level
        self.update_state()

    async def volume_mute(self, muted: bool) -> None:
        """Send VOLUME MUTE command to player."""
        command = "setPlayerCmd:mute:1" if muted else "setPlayerCmd:mute:0"
        await self._send_command(command)
        self._attr_volume_muted = muted
        self.update_state()

    async def play(self) -> None:
        """Send PLAY command to player."""
        await self._send_command("setPlayerCmd:resume")
        self._attr_playback_state = PlaybackState.PLAYING
        self.update_state()

    async def pause(self) -> None:
        """Send PAUSE command to player."""
        await self._send_command("setPlayerCmd:pause")
        self._attr_playback_state = PlaybackState.PAUSED
        self.update_state()

    async def stop(self) -> None:
        """Stop playback."""
        await self._send_command("setPlayerCmd:stop")
        self._attr_playback_state = PlaybackState.IDLE
        self._attr_current_media = None
        self.update_state()

    async def play_media(self, media: PlayerMedia) -> None:
        """Play media on the player."""
        import asyncio
        import time

        self.logger.info("🎵 PLAY_MEDIA CALLED on %s: %s", self.display_name, media.uri)

        # Stop current playback
        await self._send_command("setPlayerCmd:stop")

        # Small delay to allow stop to complete
        await asyncio.sleep(0.5)

        # Switch to wifi mode for URL streaming
        await self._send_command("setPlayerCmd:switchmode:wifi")
        await asyncio.sleep(0.5)

        # IMPORTANT: LinkPlay firmware has a bug with URLs ending in file extensions
        # (e.g., .flac, .mp3). The dot is interpreted as a command delimiter.
        # Workaround: append a query parameter to break the extension pattern.
        # Note: trailing slash doesn't work with aiohttp routing.
        uri = media.uri
        if "?" not in uri:
            uri = uri + "?linkplay=1"

        self.logger.info("🎵 Playing URI: %s", uri)

        # Use setPlayerCmd:play with the URL (no encoding needed for colons/slashes)
        result = await self._send_command(f"setPlayerCmd:play:{uri}")
        self.logger.info("🎵 Play command result: %s", result)

        if result is None:
            self.logger.warning("🎵 Play command failed")

        # Track when playback started - poll() will ignore "stop" status for 15 seconds
        self._play_start_time = time.time()

        self._attr_playback_state = PlaybackState.PLAYING
        self._attr_current_media = media
        self.update_state()
        self.logger.info("🎵 Play media completed, state updated")

    async def poll(self) -> None:
        """Poll player for current status."""
        self.logger.debug("Polling player %s at %s", self.display_name, self.ip_address)
        try:
            # First check device availability using getStatusEx (always returns data if device is online)
            device_status = await self._send_command("getStatusEx")
            if not device_status:
                self.logger.warning("Device %s not responding to getStatusEx", self.display_name)
                self._attr_available = False
                self.update_state()
                return

            # Device is available
            self._attr_available = True

            # Now get player status for playback state
            status = await self._get_status()
            self.logger.debug("Poll status for %s: %s", self.display_name, status)
            if status:
                self._update_from_status(status)
            else:
                # Empty player status is normal when player is idle - keep available
                self.logger.debug("No player status for %s (idle)", self.display_name)
                self._attr_playback_state = PlaybackState.IDLE

            self.logger.debug("Player %s available: %s", self.display_name, self._attr_available)
            self.update_state()
        except Exception as err:  # noqa: BLE001
            self.logger.error(
                "Error polling player %s: %s",
                self.display_name,
                err,
            )
            self._attr_available = False
            self.update_state()

    async def _send_command(self, command: str) -> dict | None:
        """Send command to LinkPlay device."""
        url = f"http://{self.ip_address}:{LINKPLAY_DEFAULT_PORT}/httpapi.asp?command={command}"

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=LINKPLAY_TIMEOUT)
            ) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # LinkPlay returns JSON with Content-Type: text/html
                        import json
                        text = await response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            # Some commands return non-JSON response (like "OK")
                            self.logger.debug("Non-JSON response for %s: %s", command, text)
                            return {"response": text}
        except (aiohttp.ClientError, TimeoutError) as err:
            self.logger.error(
                "Error sending command to %s: %s",
                self.display_name,
                err,
            )
            # Don't set unavailable here - let poll() handle availability

        return None

    async def _get_status(self) -> dict | None:
        """Get current status from device."""
        return await self._send_command("getPlayerStatus")

    def _update_from_status(self, status: dict) -> None:
        """Update player state from status response."""
        import time

        self._last_status = status
        self._attr_available = True

        # Update state
        play_status = status.get("status", "stop")
        if play_status == "play":
            self._attr_playback_state = PlaybackState.PLAYING
        elif play_status == "pause":
            self._attr_playback_state = PlaybackState.PAUSED
        else:
            # Grace period: don't set to IDLE within 15 seconds of play_media
            # LinkPlay devices take time to buffer and start playing
            time_since_play = time.time() - self._play_start_time
            if time_since_play < 15 and self._attr_playback_state == PlaybackState.PLAYING:
                self.logger.debug(
                    "Ignoring 'stop' status during grace period (%.1fs since play)",
                    time_since_play,
                )
            else:
                self._attr_playback_state = PlaybackState.IDLE

        # Update volume
        volume = status.get("vol", 0)
        if isinstance(volume, (int, str)):
            try:
                self._attr_volume_level = int(volume)
            except ValueError:
                pass

        # Update mute
        mute = status.get("mute", 0)
        self._attr_volume_muted = bool(int(mute)) if isinstance(mute, (int, str)) else False

        # Update current media (if needed)
        # Note: current_media is not a simple attribute, handle separately if needed

    async def set_members(
        self,
        player_ids_to_add: list[str] | None = None,
        player_ids_to_remove: list[str] | None = None,
    ) -> None:
        """Handle SET_MEMBERS command - group/ungroup LinkPlay devices for multiroom.

        :param player_ids_to_add: List of player_id's to add to this multiroom group.
        :param player_ids_to_remove: List of player_id's to remove from this multiroom group.
        """
        import asyncio

        self.logger.info(
            "set_members called on %s: add=%s, remove=%s",
            self.display_name,
            player_ids_to_add,
            player_ids_to_remove,
        )

        members_changed = False

        # Handle adding players to multiroom group
        if player_ids_to_add:
            # Initialize group member tracking if not exists
            if not hasattr(self, "_group_member_ids"):
                self._group_member_ids = []

            for player_id in player_ids_to_add:
                # Skip if player is already in the group
                if player_id in self._group_member_ids:
                    self.logger.debug("Player %s already in group, skipping", player_id)
                    continue

                slave_player = self.provider._players.get(player_id)
                if not slave_player:
                    self.logger.warning("Player %s not found in LinkPlay provider", player_id)
                    continue

                # Send join command to the slave device
                # Command format: ConnectMasterAp:JoinGroupMaster:eth<master_ip>:wifi<slave_ip>
                command = f"ConnectMasterAp:JoinGroupMaster:eth{self.ip_address}:wifi{slave_player.ip_address}"
                self.logger.info(
                    "Joining %s to master %s with command: %s",
                    slave_player.display_name,
                    self.display_name,
                    command,
                )
                result = await slave_player._send_command(command)
                self.logger.info("Join command result: %s", result)

                # Update group members tracking
                self._group_member_ids.append(player_id)
                members_changed = True

        # Handle removing players from multiroom group
        if player_ids_to_remove:
            for player_id in player_ids_to_remove:
                slave_player = self.provider._players.get(player_id)
                if not slave_player:
                    self.logger.warning("Player %s not found in LinkPlay provider", player_id)
                    continue

                # Send kickout command from the master to remove the slave
                # Command format: multiroom:SlaveKickout:<slave_ip>
                command = f"multiroom:SlaveKickout:{slave_player.ip_address}"
                self.logger.info(
                    "Kicking %s from master %s with command: %s",
                    slave_player.display_name,
                    self.display_name,
                    command,
                )
                result = await self._send_command(command)
                self.logger.info("Kickout command result: %s", result)

                # Update group members tracking
                if hasattr(self, "_group_member_ids") and player_id in self._group_member_ids:
                    self._group_member_ids.remove(player_id)
                    members_changed = True

        # IMPORTANT: LinkPlay devices need time to establish the multiroom group
        # Wait for the group to be fully formed before allowing playback commands
        if members_changed:
            self.logger.info("Waiting for multiroom group to stabilize...")
            await asyncio.sleep(2.0)
            self.logger.info("Multiroom group ready")

        self.update_state()
