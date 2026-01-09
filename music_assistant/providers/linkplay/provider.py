"""LinkPlay Player Provider implementation."""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import aiohttp

from music_assistant.helpers.util import TaskManager
from music_assistant.models.player_provider import PlayerProvider

from .constants import (
    CONF_NETWORK_SUBNET,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    LINKPLAY_DEFAULT_PORT,
    LINKPLAY_TIMEOUT,
)
from .player import LinkPlayPlayer

if TYPE_CHECKING:
    from music_assistant_models.enums import PlayerFeature


class LinkPlayProvider(PlayerProvider):
    """LinkPlay Player provider for Music Assistant."""

    _scan_task: asyncio.Task | None = None
    _players: dict[str, LinkPlayPlayer] = {}

    async def handle_async_init(self) -> None:
        """Handle async initialization of the provider."""
        self.logger.info("Initializing LinkPlay Player Provider")
        self._players = {}

    async def loaded_in_mass(self) -> None:
        """Call after the provider has been loaded."""
        self.logger.info("LinkPlay Player Provider loaded, starting discovery")
        await self.discover_players()
        # Start periodic discovery
        self._scan_task = self.mass.create_task(self._periodic_discovery())

    async def unload(self, is_removed: bool = False) -> None:
        """Handle unload/close of the provider."""
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()

        async with TaskManager(self.mass) as tg:
            for player in list(self._players.values()):
                tg.create_task(self._unregister_player(player))

    async def _periodic_discovery(self) -> None:
        """Periodically discover LinkPlay players."""
        interval = self.config.get_value(CONF_SCAN_INTERVAL) or DEFAULT_SCAN_INTERVAL
        while True:
            try:
                await asyncio.sleep(interval)
                await self.discover_players()
            except asyncio.CancelledError:
                break
            except Exception as err:  # noqa: BLE001
                self.logger.exception("Error during periodic discovery: %s", err)

    async def discover_players(self) -> None:
        """Discover LinkPlay players on the network."""
        self.logger.debug("Starting LinkPlay player discovery...")

        try:
            subnet = self.config.get_value(CONF_NETWORK_SUBNET)
            discovered = await self._scan_network(subnet)

            self.logger.info("Discovered %d LinkPlay players", len(discovered))

            for ip_address, device_info in discovered.items():
                player_id = f"linkplay_{device_info['uuid']}"
                self.logger.info("Checking player %s, already in _players: %s, _players keys: %s",
                                player_id, player_id in self._players, list(self._players.keys())[:3])

                if player_id in self._players:
                    # Player already exists, update if needed
                    player = self._players[player_id]
                    if player.ip_address != ip_address:
                        self.logger.info(
                            "Player %s IP changed from %s to %s",
                            player.display_name,
                            player.ip_address,
                            ip_address,
                        )
                        player.ip_address = ip_address
                else:
                    # New player discovered
                    await self._register_player(player_id, ip_address, device_info)

        except Exception as err:  # noqa: BLE001
            self.logger.exception("Error during player discovery: %s", err)

    async def _scan_network(self, subnet: str | None = None) -> dict[str, dict]:
        """Scan network for LinkPlay devices."""
        discovered = {}

        # Get local network IPs if subnet not specified
        if not subnet or subnet == "192.168.0.0/16":
            subnets = await self._get_local_subnets()
        else:
            subnets = [subnet]

        for subnet_str in subnets:
            self.logger.debug("Scanning subnet %s for LinkPlay devices", subnet_str)

            # Generate IP addresses to scan
            ips_to_scan = self._generate_ip_range(subnet_str)

            # Scan in batches
            batch_size = 50
            for i in range(0, len(ips_to_scan), batch_size):
                batch = ips_to_scan[i : i + batch_size]
                results = await asyncio.gather(
                    *[self._check_linkplay_device(ip) for ip in batch],
                    return_exceptions=True,
                )

                for ip, result in zip(batch, results, strict=False):
                    if result and not isinstance(result, Exception):
                        discovered[ip] = result

        return discovered

    async def _check_linkplay_device(self, ip: str) -> dict | None:
        """Check if device at IP is a LinkPlay device."""
        try:
            url = f"http://{ip}:{LINKPLAY_DEFAULT_PORT}/httpapi.asp?command=getStatusEx"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=LINKPLAY_TIMEOUT)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # LinkPlay returns JSON with Content-Type: text/html, so read as text and parse manually
                        import json
                        text = await response.text()
                        data = json.loads(text)
                        self.logger.info("Found LinkPlay device at %s: %s", ip, data.get("DeviceName", "Unknown"))
                        # Extract device info
                        return {
                            "uuid": data.get("uuid", ip.replace(".", "_")),
                            "name": data.get("DeviceName", f"LinkPlay {ip}"),
                            "model": data.get("hardware", "Unknown"),
                            "firmware": data.get("firmware", "Unknown"),
                        }
                    else:
                        self.logger.debug("Device at %s returned status %d", ip, response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self.logger.debug("Connection failed for %s: %s", ip, type(err).__name__)
        except Exception as err:  # noqa: BLE001
            self.logger.debug("Error checking device at %s: %s", ip, err)

        return None

    def _generate_ip_range(self, subnet: str) -> list[str]:
        """Generate list of IP addresses from subnet."""
        import ipaddress

        try:
            network = ipaddress.ip_network(subnet, strict=False)
            # Limit to reasonable size
            if network.num_addresses > 1024:
                self.logger.warning(
                    "Subnet %s too large (%d addresses), limiting to first 1024",
                    subnet,
                    network.num_addresses,
                )
                return [str(ip) for ip in list(network.hosts())[:1024]]
            return [str(ip) for ip in network.hosts()]
        except ValueError as err:
            self.logger.error("Invalid subnet %s: %s", subnet, err)
            return []

    async def _get_local_subnets(self) -> list[str]:
        """Get local network subnets."""
        import ipaddress

        subnets = []
        try:
            # Get hostname and local IP
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)

            # Generate /24 subnet from local IP
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            subnets.append(str(network))

        except Exception as err:  # noqa: BLE001
            self.logger.debug("Error getting local subnets: %s", err)
            # Fallback to common subnets
            subnets = ["192.168.1.0/24", "192.168.0.0/24"]

        return subnets

    async def _register_player(
        self, player_id: str, ip_address: str, device_info: dict
    ) -> None:
        """Register a new LinkPlay player."""
        self.logger.info(
            "Registering new LinkPlay player: %s at %s",
            device_info["name"],
            ip_address,
        )

        player = LinkPlayPlayer(
            provider=self,
            player_id=player_id,
            ip_address=ip_address,
            device_info=device_info,
        )

        self._players[player_id] = player
        self.logger.info("Calling register_or_update for %s", player_id)
        try:
            await self.mass.players.register_or_update(player)
            self.logger.info("Successfully registered player %s in controller", player_id)
        except Exception as e:
            self.logger.exception("Failed to register player %s: %s", player_id, e)

    async def _unregister_player(self, player: LinkPlayPlayer) -> None:
        """Unregister a LinkPlay player."""
        self.logger.info("Unregistering LinkPlay player: %s", player.display_name)
        if player.player_id in self._players:
            del self._players[player.player_id]
        # Use unregister with permanent=False to keep the config for next startup
        await self.mass.players.unregister(player.player_id, permanent=False)
