# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutterCJH)

"""Propagation scoring — estimates likelihood of contacting a spotted activator.

Uses two complementary signals:
  1. Empirical: distances of QSOs actually made this session, per band.
  2. Theoretical: skip zone calculation from ionospheric critical frequency (fof2).

Empirical data wins when available (≥3 QSOs with distance on the band).
Theory serves as a fallback when the session is young.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from potatui.adif import freq_to_band

_F2_HEIGHT_KM = 300.0       # typical F2 ionospheric layer height
_SINGLE_HOP_MAX_KM = 4000.0  # practical single-hop ceiling
_MIN_EMPIRICAL = 3           # minimum QSOs needed to use empirical scoring


@dataclass
class PropProfile:
    """Live propagation profile for the current activation."""

    # Per-band lists of confirmed QSO distances (km) from this session
    band_distances: dict[str, list[float]] = field(default_factory=dict)

    # Critical frequency and MUF from prop.kc2g.com (updated every 10 min)
    fof2_mhz: float | None = None
    muf_mhz: float | None = None

    def add_qso(self, band: str, distance_km: float) -> None:
        """Record a successfully logged QSO distance for this band."""
        self.band_distances.setdefault(band, []).append(distance_km)


class PropScore(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _theoretical_score(fof2_mhz: float, fo_mhz: float, dist_km: float) -> PropScore:
    """Score based purely on skip-zone physics."""
    if fof2_mhz >= fo_mhz:
        # Critical freq above operating freq → NVIS, no skip zone
        if dist_km <= 500:
            return PropScore.HIGH
        elif dist_km <= 1200:
            return PropScore.MEDIUM
        else:
            return PropScore.LOW

    # Skip zone exists: compute minimum reachable distance
    ratio = min(fof2_mhz / fo_mhz, 1.0)
    mua = math.asin(ratio)                              # max usable elevation angle
    skip_km = 2.0 * _F2_HEIGHT_KM * math.tan(math.pi / 2.0 - mua)

    if dist_km < skip_km * 0.8:
        return PropScore.LOW          # solidly in skip zone
    elif dist_km < skip_km * 1.3:
        return PropScore.MEDIUM       # near the skip zone edge
    elif dist_km <= _SINGLE_HOP_MAX_KM:
        return PropScore.HIGH         # comfortable single-hop range
    elif dist_km <= _SINGLE_HOP_MAX_KM * 2.0:
        return PropScore.MEDIUM       # multi-hop — possible but uncertain
    else:
        return PropScore.LOW


def score_spot(
    profile: PropProfile,
    spot_freq_khz: float,
    dist_km: float | None,
) -> PropScore:
    """Return the likelihood of contacting this spot.

    Empirical QSO distances from the current session take priority.
    Falls back to theoretical skip-zone calculation when data is sparse.
    """
    if dist_km is None:
        return PropScore.UNKNOWN

    fo_mhz = spot_freq_khz / 1000.0
    band = freq_to_band(spot_freq_khz)

    emp_distances = profile.band_distances.get(band, [])
    has_empirical = len(emp_distances) >= _MIN_EMPIRICAL

    theoretical: PropScore | None = None
    if profile.muf_mhz is not None and fo_mhz > profile.muf_mhz:
        # Operating frequency above MUF — skywave propagation not possible on this band.
        # Note: ideally mufd would be evaluated at the midpoint of each path rather than
        # at the park location, since that's where F2 signals actually reflect. However,
        # prop.kc2g.com is rate-limited to once per 15 min per location, making per-spot
        # midpoint queries impractical (~50-100 unique midpoints per spots list).
        # For typical POTA domestic paths (300–2000 mi) the park-location MUF is a
        # reasonable proxy — both endpoints are usually in the same solar-illumination
        # zone. Accuracy degrades on DX paths with midpoints at very different latitudes.
        theoretical = PropScore.LOW
    elif profile.fof2_mhz is not None:
        theoretical = _theoretical_score(profile.fof2_mhz, fo_mhz, dist_km)

    if not has_empirical:
        return theoretical if theoretical is not None else PropScore.UNKNOWN

    # --- Empirical scoring ---
    min_d = min(emp_distances)
    max_d = max(emp_distances)

    if min_d * 0.9 <= dist_km <= max_d * 1.25:
        emp_score = PropScore.HIGH
    elif (min_d * 0.6 <= dist_km < min_d * 0.9) or (max_d * 1.25 < dist_km <= max_d * 2.0):
        emp_score = PropScore.MEDIUM
    else:
        emp_score = PropScore.LOW

    if theoretical is None:
        return emp_score

    # Empirical HIGH is definitive; empirical LOW softened if theory says HIGH
    if emp_score == PropScore.HIGH:
        return PropScore.HIGH
    if emp_score == PropScore.LOW and theoretical == PropScore.HIGH:
        return PropScore.MEDIUM
    return emp_score
