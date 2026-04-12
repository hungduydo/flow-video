"""Platform composition modules - pluggable architecture for easy platform addition."""

from .base import ComposePlatform, VideoPaths, ComposeConfig
from .youtube import YouTubeCompose
from .tiktok import TikTokPortrait, TikTokBlurBg


# Platform registry — add new platforms here
_PLATFORMS = {
    "youtube": YouTubeCompose(),
    "tiktok_portrait": TikTokPortrait(),
    "tiktok_blur_bg": TikTokBlurBg(),
}


def get_platform(name: str) -> ComposePlatform:
    """Get a composition platform by name.
    
    Args:
        name: platform name ("youtube", "tiktok_portrait", "tiktok_blur_bg")
        
    Returns:
        ComposePlatform instance
        
    Raises:
        ValueError: if platform not found
    """
    if name not in _PLATFORMS:
        available = ", ".join(_PLATFORMS.keys())
        raise ValueError(f"Unknown platform: {name!r}. Available: {available}")
    return _PLATFORMS[name]


def register_platform(name: str, platform: ComposePlatform) -> None:
    """Register a new composition platform.
    
    Use this to add custom platforms at runtime:
    
    Example:
        from platforms import register_platform
        from my_platform import MyCustomPlatform
        
        register_platform("custom", MyCustomPlatform())
    """
    if name in _PLATFORMS:
        raise ValueError(f"Platform {name!r} already registered")
    _PLATFORMS[name] = platform


def list_platforms() -> list[str]:
    """List all registered platforms."""
    return list(_PLATFORMS.keys())


__all__ = [
    "ComposePlatform",
    "VideoPaths",
    "ComposeConfig",
    "get_platform",
    "register_platform",
    "list_platforms",
]
