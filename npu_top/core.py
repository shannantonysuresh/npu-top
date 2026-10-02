"""Pure logic: turn raw Windows "GPU Engine" counter samples into per-adapter and per-process usage.

Instance names look like:  pid_4812_luid_0x00000000_0x0001013A_phys_0_eng_3_engtype_Neural
"""
import re
from collections import defaultdict

_INSTANCE = re.compile(r"pid_(\d+)_luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)_phys_(\d+)_eng_(\d+)_engtype_(.+)$")


def parse_instance(name):
    """-> (pid, adapter, engine, engtype) or None for names that don't match."""
    m = _INSTANCE.match(name)
    if not m:
        return None
    pid, luid, phys, eng, engtype = m.groups()
    return int(pid), f"{luid.lower()}_{phys}", int(eng), engtype.strip().lower()


def aggregate(samples):
    """samples: {instance_name: utilization %}.

    Like Task Manager: an engine's load is the sum over processes; an adapter's load is its busiest engine.
    An adapter with a 'neural' engine is the NPU, one with a '3d' engine is a GPU.
    Returns {adapter: {"kind", "util", "procs": {pid: util}}}.
    """
    engines = defaultdict(float)                      # (adapter, engine) -> summed %
    per_proc = defaultdict(lambda: defaultdict(float))  # (adapter, pid, engine) -> %
    types = defaultdict(set)
    for name, value in samples.items():
        parsed = parse_instance(name)
        if parsed is None:
            continue
        pid, adapter, eng, engtype = parsed
        engines[adapter, eng] += value
        per_proc[adapter, pid][eng] += value
        types[adapter].add(engtype)

    out = {}
    for adapter, kinds in types.items():
        kind = "NPU" if "neural" in kinds else "GPU" if "3d" in kinds else "other"
        util = max(v for (a, _), v in engines.items() if a == adapter)
        procs = {pid: min(max(e.values()), 100.0) for (a, pid), e in per_proc.items()
                 if a == adapter and max(e.values()) > 0}
        out[adapter] = {"kind": kind, "util": min(util, 100.0), "procs": procs}
    return out


def by_kind(adapters, kind):
    """Busiest adapter of a kind (most machines have one NPU and one GPU), or None."""
    found = [a for a in adapters.values() if a["kind"] == kind]
    return max(found, key=lambda a: a["util"]) if found else None


def summarize(values):
    """Peak / average / share of samples above 50%, for --watch reports."""
    if not values:
        return {"peak": 0.0, "avg": 0.0, "busy": 0.0}
    return {"peak": max(values), "avg": sum(values) / len(values),
            "busy": sum(v >= 50 for v in values) / len(values)}
