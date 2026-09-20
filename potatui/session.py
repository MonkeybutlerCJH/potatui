# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Session and QSO data models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class QSO:
    qso_id: int
    timestamp_utc: datetime
    callsign: str
    rst_sent: str
    rst_rcvd: str
    freq_khz: float
    band: str
    mode: str
    name: str = ""
    state: str = ""
    notes: str = ""
    is_p2p: bool = False
    p2p_ref: str = ""
    operator: str = ""
    contact_grid: str = ""
    distance_km: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp_utc"] = self.timestamp_utc.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> QSO:
        d = dict(d)
        d["timestamp_utc"] = datetime.fromisoformat(d["timestamp_utc"])
        d.setdefault("state", "")
        d.setdefault("operator", "")
        d.setdefault("contact_grid", "")
        d.setdefault("distance_km", None)
        return cls(**d)


@dataclass
class Session:
    operator: str
    station_callsign: str
    park_refs: list[str]
    active_park_ref: str
    grid: str
    rig: str
    antenna: str
    power_w: int
    start_time: datetime
    my_state: str = ""   # MY_STATE for ADIF (required when park spans multiple states)
    qsos: list[QSO] = field(default_factory=list)

    # Runtime state (not serialized)
    _next_id: int = field(default=1, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.qsos:
            self._next_id = max(q.qso_id for q in self.qsos) + 1

    def add_qso(
        self,
        callsign: str,
        rst_sent: str,
        rst_rcvd: str,
        freq_khz: float,
        band: str,
        mode: str,
        name: str = "",
        state: str = "",
        notes: str = "",
        is_p2p: bool = False,
        p2p_ref: str = "",
        operator: str = "",
        contact_grid: str = "",
        distance_km: float | None = None,
        timestamp_utc: datetime | None = None,
    ) -> QSO:
        qso = QSO(
            qso_id=self._next_id,
            timestamp_utc=timestamp_utc or datetime.utcnow(),
            callsign=callsign.upper(),
            rst_sent=rst_sent,
            rst_rcvd=rst_rcvd,
            freq_khz=freq_khz,
            band=band,
            mode=mode,
            name=name,
            state=state,
            notes=notes,
            is_p2p=is_p2p,
            p2p_ref=p2p_ref,
            operator=operator,
            contact_grid=contact_grid,
            distance_km=distance_km,
        )
        self._next_id += 1
        self.qsos.append(qso)
        return qso

    def remove_qso(self, qso_id: int) -> bool:
        before = len(self.qsos)
        self.qsos = [q for q in self.qsos if q.qso_id != qso_id]
        return len(self.qsos) < before

    def update_qso(self, qso_id: int, **kwargs) -> QSO | None:
        for i, q in enumerate(self.qsos):
            if q.qso_id == qso_id:
                for k, v in kwargs.items():
                    setattr(self.qsos[i], k, v)
                return self.qsos[i]
        return None

    def is_duplicate(
        self,
        callsign: str,
        band: str = "",
        same_utc_date: bool = False,
        utc_now: datetime | None = None,
    ) -> bool:
        """Return True when ``callsign`` has already been worked.

        A match on the same callsign (and, when ``band`` is given, the same
        band) is a duplicate.  When ``same_utc_date`` is True, only QSOs logged
        on the current UTC date count — a new UTC date is a new POTA activation
        and contacts from a previous date are no longer duplicates.

        ``utc_now`` overrides the reference time (used by tests).
        """
        cs = callsign.upper()
        today = (utc_now or datetime.utcnow()).date()
        for q in self.qsos:
            if q.callsign != cs:
                continue
            if band and q.band != band:
                continue
            if same_utc_date and q.timestamp_utc.date() != today:
                continue
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "operator": self.operator,
            "station_callsign": self.station_callsign,
            "park_refs": self.park_refs,
            "active_park_ref": self.active_park_ref,
            "grid": self.grid,
            "rig": self.rig,
            "antenna": self.antenna,
            "power_w": self.power_w,
            "start_time": self.start_time.isoformat(),
            "my_state": self.my_state,
            "qsos": [q.to_dict() for q in self.qsos],
        }

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        d = dict(d)
        d["start_time"] = datetime.fromisoformat(d["start_time"])
        d["qsos"] = [QSO.from_dict(q) for q in d.get("qsos", [])]
        d.setdefault("my_state", "")
        d.setdefault("station_callsign", d["operator"])
        return cls(**d)

    @classmethod
    def load_json(cls, path: str) -> Session:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
