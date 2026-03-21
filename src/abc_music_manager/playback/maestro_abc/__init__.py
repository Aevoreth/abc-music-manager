"""
Maestro ABC-to-MIDI port: self-contained ABC conversion engine.
Handles complex time signatures that music21 cannot.
"""

from .abc_to_midi import abc_to_midi as maestro_abc_to_midi

__all__ = ["maestro_abc_to_midi"]
