"""Decode Elite Dangerous Status.json flag bitfields.

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
    """Return a shallow copy of a Status.json object with decoded flag fields.

    Raw ``Flags`` and ``Flags2`` values are preserved exactly. A missing or
    malformed bitfield remains unavailable and does not gain derived fields.
    Unknown active bits are reported by bit position so future game additions
    cannot silently disappear.
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

    return result
