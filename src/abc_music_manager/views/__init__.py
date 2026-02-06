# UI views: Settings, Library, Song Detail

from .settings_view import build_settings_view
from .library_view import build_library_view
from .song_detail_view import build_song_detail_view

__all__ = ["build_settings_view", "build_library_view", "build_song_detail_view"]
