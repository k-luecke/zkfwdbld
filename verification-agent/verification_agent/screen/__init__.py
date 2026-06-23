"""Pre-screening tools (Move A) — select a target by bug-class SHAPE, not category.

Shape-fit (shape.py) runs the M0 surface + Move-2 sibling-asymmetry + Seer
reachability as a pre-screen, from code structure alone — never on judged findings.
Dual-use: the same tool selects which LIVE competition fits the agent's class.
"""

from .shape import ShapeFitReport, ShapeScreener

__all__ = ["ShapeScreener", "ShapeFitReport"]
