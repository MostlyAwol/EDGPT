"""Decode Elite Dangerous Status.json numeric values.

Definitions come from section 14 of Frontier's Journal Manual v32:
https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf

The public names below are stable, unlocalized identifiers normalized from the
manual's human-readable labels. Keep the tuples in ascending bit order so the
decoded output is deterministic.
"""


STATUS_FLAG_NAMES = (
    "Docked",
    "Landed",
    "LandingGearDown",
    "ShieldsUp",
    "Supercruise",
    "FlightAssistOff",
    "HardpointsDeployed",
    "InWing",
    "LightsOn",
    "CargoScoopDeployed",
    "SilentRunning",
    "ScoopingFuel",
    "SrvHandbrake",
    "SrvUsingTurretView",
    "SrvTurretRetracted",
    "SrvDriveAssist",
    "FsdMassLocked",
    "FsdCharging",
    "FsdCooldown",
    "LowFuel",
    "OverHeating",
    "HasLatLong",
    "IsInDanger",
    "BeingInterdicted",
    "InMainShip",
    "InFighter",
    "InSrv",
    "HudInAnalysisMode",
    "NightVision",
    "AltitudeFromAverageRadius",
    "FsdJump",
    "SrvHighBeam",
)

STATUS_FLAG2_NAMES = (
    "OnFoot",
    "InTaxi",
    "InMulticrew",
    "OnFootInStation",
    "OnFootOnPlanet",
    "AimDownSight",
    "LowOxygen",
    "LowHealth",
    "Cold",
    "Hot",
    "VeryCold",
    "VeryHot",
    "GlideMode",
    "OnFootInHangar",
    "OnFootSocialSpace",
    "OnFootExterior",
    "BreathableAtmosphere",
    "Telepresence Multicrew",
    "Physical Multicrew",
    "FSD Hyperdrive Charging",
    "Supercruise Overdrive (SCO) Active",
    "Supercruise Assist Active",
)

GUI_FOCUS_NAMES = (
    "No GUI screen focused (normal cockpit view)",
    "Internal Panel",
    "External Panel",
    "Comms Panel",
    "Role Panel",
    "Station Services",
    "Galaxy Map",
    "System Map",
    "System Orrery View",
    "Full Spectrum System Scanner",
    "Detailed Surface Scanner",
    "Codex",
)


def _decode_bitfield(value, names):
    """Return active names and unknown bit positions for a non-negative int."""
    decoded = [name for bit, name in enumerate(names) if value & (1 << bit)]
    unknown_mask = value & ~((1 << len(names)) - 1)
    unknown_bits = [
        bit for bit in range(unknown_mask.bit_length()) if unknown_mask & (1 << bit)
    ]
    return decoded, unknown_bits


def decode_status_flags(status):
    """Return a shallow copy of Status.json with decoded numeric fields.

    Raw ``Flags`` and ``Flags2`` values are preserved exactly. A missing or
    malformed bitfield remains unavailable and does not gain derived fields.
    Unknown active bits are reported by bit position so future game additions
    cannot silently disappear. A documented ``GuiFocus`` integer gains its
    corresponding human-readable label without replacing the raw value.
    """
    if not isinstance(status, dict):
        return status

    result = dict(status)
    for raw_name, decoded_name, unknown_name, names in (
        ("Flags", "FlagsDecoded", "FlagsUnknownBits", STATUS_FLAG_NAMES),
        ("Flags2", "Flags2Decoded", "Flags2UnknownBits", STATUS_FLAG2_NAMES),
    ):
        value = status.get(raw_name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            decoded, unknown = _decode_bitfield(value, names)
            result[decoded_name] = decoded
            result[unknown_name] = unknown

    gui_focus = status.get("GuiFocus")
    if (
        isinstance(gui_focus, int)
        and not isinstance(gui_focus, bool)
        and 0 <= gui_focus < len(GUI_FOCUS_NAMES)
    ):
        result["GuiFocusDecoded"] = GUI_FOCUS_NAMES[gui_focus]

    return result
