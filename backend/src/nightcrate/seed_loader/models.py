"""Seed loader data models (dataclasses)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class TableReport:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_user_modified: list[str] = field(default_factory=list)
    skipped_corrupt: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


@dataclass
class SeedError:
    table: str
    seed_key: str | None
    message: str
    exception: str | None = None


@dataclass
class SeedReport:
    mode: Literal["first_run", "update"]
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    per_table: dict[str, TableReport] = field(default_factory=dict)
    errors: list[SeedError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0
