def corner_width(spans, right, vertical, pitch):
    """P.21: four actual half-spans or two 15-panel modules, clipped at the edge."""
    if vertical:
        return min(sum(spans), 30*pitch)
    return sum(spans[-2:] if right else spans[:2])
