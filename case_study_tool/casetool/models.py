"""Model presets, MARS parameters and output-step rules."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# (up_to_step, interval_h): steps <= up_to_step exist every interval_h hours.
IFS_STEPS = ((90, 1), (144, 3), (360, 6))
AIFS_STEPS = ((360, 6),)
DESTINE_STEPS = ((120, 1),)


@dataclass(frozen=True)
class ModelSpec:
    """MARS identification and output characteristics of one forecast model."""

    key: str
    label: str
    mars_class: str
    expver: str
    stream: str = "oper"
    mars_type: str = "fc"
    fallback_expvers: tuple[str, ...] = ()
    step_rules: tuple[tuple[int, int], ...] = IFS_STEPS
    cycles: tuple[int, ...] = (0, 12)
    extra: dict = field(default_factory=dict)

    @property
    def expvers(self) -> tuple[str, ...]:
        """Return the experiment versions to try, in order."""
        return (self.expver, *self.fallback_expvers)

    def interval_at(self, step: int) -> int | None:
        """Return the output interval (h) that applies at ``step``, or None beyond range."""
        for upto, interval in self.step_rules:
            if step <= upto:
                return interval
        return None

    def has_step(self, step: int) -> bool:
        """Whether the model archives output at ``step``."""
        interval = self.interval_at(step)
        return interval is not None and step % interval == 0

    def steps_between(self, s0: int, s1: int, min_interval: int = 1) -> list[int]:
        """Return archived steps in [s0, s1] spaced at least ``min_interval`` hours."""
        return [
            s
            for s in range(s0, s1 + 1)
            if self.has_step(s) and (s - s0) % min_interval == 0
        ]

    def param(self, variable: str) -> str:
        """Return the MARS param string for ``variable`` in this model's class."""
        table = RD_PARAMS if self.mars_class == "rd" else OPER_PARAMS
        return table[variable]


OPER_PARAMS = {"tp": "228", "ws10": "165/166", "orog": "129/172"}
RD_PARAMS = {"tp": "228.128", "ws10": "165.128/166.128", "orog": "129/172"}

PRESETS: dict[str, ModelSpec] = {
    "ifs": ModelSpec("ifs", "IFS operational", "od", "0001"),
    "aifs": ModelSpec(
        "aifs",
        "AIFS-single",
        "ai",
        "0001",
        step_rules=AIFS_STEPS,
        cycles=(0, 6, 12, 18),
    ),
    "destine": ModelSpec(
        "destine",
        "DestinE",
        "rd",
        "iekm",
        fallback_expvers=("i4ql",),
        step_rules=DESTINE_STEPS,
        cycles=(0,),
    ),
    "pilot_dt": ModelSpec(
        "pilot_dt", "Pilot DT", "rd", "j5j2", step_rules=DESTINE_STEPS, cycles=(0,)
    ),
}


def model_from_config(entry) -> ModelSpec:
    """Build a ModelSpec from a preset name or a mapping in the case file.

    Accepted forms::

        - ifs
        - {preset: destine, expver: j5j2, label: "DestinE j5j2"}
        - {label: "My exp", class: rd, expver: abcd, step_rules: [[120, 1]]}
    """
    if isinstance(entry, str):
        if entry not in PRESETS:
            raise ValueError(
                f"Unknown model preset {entry!r}; known: {sorted(PRESETS)}"
            )
        return PRESETS[entry]
    if not isinstance(entry, dict):
        raise ValueError(f"Model entry must be a name or a mapping, got {entry!r}")
    entry = dict(entry)
    if "preset" in entry:
        preset = entry.pop("preset")
        if preset not in PRESETS:
            raise ValueError(
                f"Unknown model preset {preset!r}; known: {sorted(PRESETS)}"
            )
        base = PRESETS[preset]
        updates = {}
        if "expver" in entry:
            updates["expver"] = str(entry.pop("expver"))
            updates["fallback_expvers"] = ()
            updates["key"] = f"{base.key}_{updates['expver']}"
            # Keep it distinguishable from the plain preset in titles and tables.
            updates["label"] = f"{base.label} {updates['expver']}"
    else:
        for required in ("class", "expver"):
            if required not in entry:
                raise ValueError(f"Custom model needs '{required}': {entry!r}")
        expver = str(entry.pop("expver"))
        base = ModelSpec(
            key=entry.pop("key", f"{entry['class']}_{expver}"),
            label=entry.pop("label", f"{entry['class']}/{expver}"),
            mars_class=entry.pop("class"),
            expver=expver,
        )
        updates = {}
    mapping = {
        "label": "label",
        "key": "key",
        "stream": "stream",
        "type": "mars_type",
        "fallback_expvers": "fallback_expvers",
        "cycles": "cycles",
    }
    for src, dst in mapping.items():
        if src in entry:
            value = entry.pop(src)
            updates[dst] = tuple(value) if isinstance(value, list) else value
    if "step_rules" in entry:
        updates["step_rules"] = tuple(tuple(r) for r in entry.pop("step_rules"))
    if "extra" in entry:
        updates["extra"] = dict(entry.pop("extra"))
    if entry:
        raise ValueError(f"Unknown model option(s) {sorted(entry)}")
    return replace(base, **updates)
