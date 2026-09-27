import sys
import unittest
from pathlib import Path


BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

from status_flags import (
    GUI_FOCUS_NAMES,
    STATUS_FLAG2_NAMES,
    STATUS_FLAG_NAMES,
    decode_status_flags,
)


class StatusFlagDecoderTests(unittest.TestCase):
    def test_every_documented_gui_focus_value_decodes(self):
        for value, name in enumerate(GUI_FOCUS_NAMES):
            with self.subTest(value=value, name=name):
                decoded = decode_status_flags({"GuiFocus": value})
                self.assertEqual(decoded["GuiFocus"], value)
                self.assertEqual(decoded["GuiFocusDecoded"], name)

    def test_zero_flags_produce_empty_deterministic_lists(self):
        decoded = decode_status_flags({"Flags": 0, "Flags2": 0})

        self.assertEqual(decoded["FlagsDecoded"], [])
        self.assertEqual(decoded["FlagsUnknownBits"], [])
        self.assertEqual(decoded["Flags2Decoded"], [])
        self.assertEqual(decoded["Flags2UnknownBits"], [])

    def test_every_documented_flag_decodes_individually(self):
        for bit, name in enumerate(STATUS_FLAG_NAMES):
            with self.subTest(field="Flags", bit=bit, name=name):
                decoded = decode_status_flags({"Flags": 1 << bit})
                self.assertEqual(decoded["FlagsDecoded"], [name])
                self.assertEqual(decoded["FlagsUnknownBits"], [])

        for bit, name in enumerate(STATUS_FLAG2_NAMES):
            with self.subTest(field="Flags2", bit=bit, name=name):
                decoded = decode_status_flags({"Flags2": 1 << bit})
                self.assertEqual(decoded["Flags2Decoded"], [name])
                self.assertEqual(decoded["Flags2UnknownBits"], [])

    def test_representative_combination_is_in_ascending_bit_order(self):
        decoded = decode_status_flags(
            {"Flags": (1 << 24) | (1 << 3) | (1 << 0), "Flags2": 5}
        )

        self.assertEqual(decoded["FlagsDecoded"], ["Docked", "ShieldsUp", "InMainShip"])
        self.assertEqual(decoded["Flags2Decoded"], ["OnFoot", "InMulticrew"])

    def test_unknown_high_bits_are_explicit(self):
        decoded = decode_status_flags(
            {"Flags": (1 << 40) | 1, "Flags2": (1 << 31) | (1 << 16)}
        )

        self.assertEqual(decoded["FlagsDecoded"], ["Docked"])
        self.assertEqual(decoded["FlagsUnknownBits"], [40])
        self.assertEqual(decoded["Flags2Decoded"], ["BreathableAtmosphere"])
        self.assertEqual(decoded["Flags2UnknownBits"], [31])

    def test_missing_fields_remain_unavailable(self):
        decoded = decode_status_flags({"event": "Status"})

        self.assertNotIn("FlagsDecoded", decoded)
        self.assertNotIn("FlagsUnknownBits", decoded)
        self.assertNotIn("Flags2Decoded", decoded)
        self.assertNotIn("Flags2UnknownBits", decoded)
        self.assertNotIn("GuiFocusDecoded", decoded)

    def test_official_status_fixture_and_raw_integer_are_preserved(self):
        raw = {"event": "Status", "Flags": 16842765}
        decoded = decode_status_flags(raw)

        self.assertEqual(decoded["Flags"], 16842765)
        self.assertEqual(
            decoded["FlagsDecoded"],
            ["Docked", "LandingGearDown", "ShieldsUp", "FsdMassLocked", "InMainShip"],
        )
        self.assertEqual(decoded["FlagsUnknownBits"], [])
        self.assertNotIn("Flags2Decoded", decoded)
        self.assertEqual(raw, {"event": "Status", "Flags": 16842765})

    def test_malformed_values_are_preserved_without_guessing(self):
        raw = {"Flags": "1", "Flags2": True, "GuiFocus": "6"}
        self.assertEqual(decode_status_flags(raw), raw)

    def test_unknown_gui_focus_value_is_preserved_without_a_guessed_label(self):
        raw = {"GuiFocus": 12}
        decoded = decode_status_flags(raw)

        self.assertEqual(decoded["GuiFocus"], 12)
        self.assertNotIn("GuiFocusDecoded", decoded)


if __name__ == "__main__":
    unittest.main()
