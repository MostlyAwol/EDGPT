"""Ordered, independent curiosity detectors for merged system maps.

Rules must return formatted strings in deterministic order and never mutate
their input. No detectors are enabled in the initial implementation.
"""

CURIOSITY_RULES = ()


def find_curiosities(system_map) -> list[str]:
    results = []
    for rule in CURIOSITY_RULES:
        results.extend(rule(system_map))
    return results
