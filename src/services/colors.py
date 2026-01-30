"""
Color Service - Generates visually distinguishable colors for categorical data.

Usage:
    from services import colors
    
    # Get colors for a list of items
    color_map = colors.assign(['c', 'e', 'm', 'n'])
    # Returns: {'c': '#...', 'e': '#...', ...}
    
    # Or generate n colors
    palette = colors.generate(8)
    # Returns: ['#...', '#...', ...]
"""

import colorsys


def generate(n, saturation=0.65, lightness=0.55):
    """
    Generate n visually distinguishable colors.
    
    Uses golden ratio spacing in hue for optimal visual separation.
    
    Args:
        n: Number of colors to generate
        saturation: Color saturation (0-1)
        lightness: Color lightness (0-1)
    
    Returns:
        List of hex color strings
    """
    if n <= 0:
        return []
    
    colors = []
    golden_ratio = 0.618033988749895
    hue = 0.0
    
    for _ in range(n):
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_color = f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'
        colors.append(hex_color)
        hue = (hue + golden_ratio) % 1.0
    
    return colors


def assign(items, saturation=0.65, lightness=0.55):
    """
    Assign colors to a list of items.
    
    Args:
        items: List of item identifiers (strings, etc.)
        saturation: Color saturation (0-1)
        lightness: Color lightness (0-1)
    
    Returns:
        Dict mapping each item to its hex color
    """
    palette = generate(len(items), saturation, lightness)
    return {item: color for item, color in zip(items, palette)}
