"""LinkPlay Player Provider for Music Assistant.

Supports LinkPlay/WiiM audio devices including:
- WiiM Mini, Pro, Amp, Ultra
- Arylic devices
- Audio Pro speakers
- And other LinkPlay-based devices
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueType
from music_assistant_models.enums import ConfigEntryType, ProviderFeature

from .constants import CONF_NETWORK_SUBNET, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DEFAULT_SUBNET
from .provider import LinkPlayProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant import MusicAssistant
    from music_assistant.models import ProviderInstanceType

SUPPORTED_FEATURES = {
    ProviderFeature.SYNC_PLAYERS,
}


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return LinkPlayProvider(mass, manifest, config, SUPPORTED_FEATURES)


async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """
    Return Config entries to setup this provider.

    :param mass: MusicAssistant instance
    :param instance_id: id of an existing provider instance (None if new instance setup).
    :param action: [optional] action key called from config entries UI.
    :param values: the (intermediate) raw values for config entries sent with the action.
    """
    # ruff: noqa: ARG001
    return (
        ConfigEntry(
            key=CONF_NETWORK_SUBNET,
            type=ConfigEntryType.STRING,
            label="Network subnet for discovery",
            default_value=DEFAULT_SUBNET,
            description="Network subnet to scan for LinkPlay devices (e.g., 192.168.1.0/24). "
            "Leave default to scan common subnets.",
        ),
        ConfigEntry(
            key=CONF_SCAN_INTERVAL,
            type=ConfigEntryType.INTEGER,
            label="Scan interval (seconds)",
            default_value=DEFAULT_SCAN_INTERVAL,
            description="How often to scan for new LinkPlay devices.",
        ),
    )
