"""Session and QSO data models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp_utc"] = self.timestamp_utc.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "QSO":
        d = dict(d)
        d["timestamp_utc"] = datetime.fromisoformat(d["timestamp_utc"])
        d.setdefault("state", "")
        return cls(**d)


@dataclass
class Session:
    operator: str
    park_refs: list[str]
    active_park_ref: str
    grid: str
    rig: str
    antenna: str
    power_w: int
    start_time: datetime
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
    ) -> QSO:
        qso = QSO(
            qso_id=self._next_id,
            timestamp_utc=datetime.utcnow(),
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
        )
        self._next_id += 1
        self.qsos.append(qso)
        return qso

    def remove_qso(self, qso_id: int) -> bool:
        before = len(self.qsos)
        self.qsos = [q for q in self.qsos if q.qso_id != qso_id]
        return len(self.qsos) < before

    def update_qso(self, qso_id: int, **kwargs) -> Optional[QSO]:
        for i, q in enumerate(self.qsos):
            if q.qso_id == qso_id:
                for k, v in kwargs.items():
                    setattr(self.qsos[i], k, v)
                return self.qsos[i]
        return None

    def is_duplicate(self, callsign: str, band: str = "") -> bool:
        cs = callsign.upper()
        if band:
            return any(q.callsign == cs and q.band == band for q in self.qsos)
        return any(q.callsign == cs for q in self.qsos)

    def to_dict(self) -> dict:
        return {
            "operator": self.operator,
            "park_refs": self.park_refs,
            "active_park_ref": self.active_park_ref,
            "grid": self.grid,
            "rig": self.rig,
            "antenna": self.antenna,
            "power_w": self.power_w,
            "start_time": self.start_time.isoformat(),
            "qsos": [q.to_dict() for q in self.qsos],
        }

    def save_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        d = dict(d)
        d["start_time"] = datetime.fromisoformat(d["start_time"])
        d["qsos"] = [QSO.from_dict(q) for q in d.get("qsos", [])]
        return cls(**d)

    @classmethod
    def load_json(cls, path: str) -> "Session":
        with open(path) as f:
            return cls.from_dict(json.load(f))
