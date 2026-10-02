"""npu-top: live CPU / GPU / NPU usage in the terminal, with per-process NPU attribution."""
import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime

from . import __version__
from .core import aggregate, by_kind, summarize
from .pdh import Query, process_name

CPU = r"\Processor Information(_Total)\% Processor Utility"
ENGINES = r"\GPU Engine(*)\Utilization Percentage"
BAR = 30


def bar(pct):
    filled = round(min(pct, 100) / 100 * BAR)
    return "█" * filled + "░" * (BAR - filled)


def sample(q):
    q.collect()
    cpu = min(q.values(CPU).get("_Total", 0.0), 100.0)
    adapters = aggregate(q.values(ENGINES))
    gpu, npu = by_kind(adapters, "GPU"), by_kind(adapters, "NPU")
    return cpu, gpu, npu


def top(adapter, n=3):
    procs = sorted((adapter or {}).get("procs", {}).items(), key=lambda kv: -kv[1])
    return [(process_name(pid), pid, v) for pid, v in procs[:n] if v >= 0.5]


def render(cpu, gpu, npu):
    lines = [f"npu-top {__version__}   {datetime.now():%H:%M:%S}   (Ctrl+C to quit)", ""]
    for label, util in [("CPU", cpu), ("GPU", gpu and gpu["util"]), ("NPU", npu and npu["util"])]:
        lines.append(f"  {label}  {'not found':>36}" if util is None else f"  {label}  {bar(util)} {util:5.1f}%")
    for label, adapter in [("NPU", npu), ("GPU", gpu)]:
        procs = top(adapter)
        if procs:
            lines += ["", f"  {label} by process:"] + [f"    {name:<28} pid {pid:<7} {v:5.1f}%" for name, pid, v in procs]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="npu-top", description=__doc__)
    ap.add_argument("-i", "--interval", type=float, default=1.0, help="seconds between samples (default 1)")
    ap.add_argument("--log", metavar="CSV", help="also append every sample to this CSV file")
    ap.add_argument("--once", action="store_true", help="print one sample and exit")
    ap.add_argument("--version", action="version", version=f"npu-top {__version__}")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="after --: run this command, then report its NPU/GPU/CPU usage, e.g. npu-top -- python infer.py")
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd

    try:
        q = Query([CPU, ENGINES])
    except OSError as e:
        sys.exit(f"npu-top: {e}")
    os.system("")  # enable ANSI escape codes in the classic Windows console
    log = open(args.log, "a", newline="") if args.log else None
    writer = csv.writer(log) if log else None
    if writer and log.tell() == 0:
        writer.writerow(["time", "cpu", "gpu", "npu", "npu_top_process"])

    child = subprocess.Popen(cmd) if cmd else None
    history = {"CPU": [], "GPU": [], "NPU": [], "child NPU": []}
    try:
        while True:
            time.sleep(args.interval)
            cpu, gpu, npu = sample(q)
            npu_top = top(npu, 1)
            if writer:
                writer.writerow([f"{datetime.now():%Y-%m-%d %H:%M:%S}", f"{cpu:.1f}",
                                 f"{gpu['util']:.1f}" if gpu else "", f"{npu['util']:.1f}" if npu else "",
                                 npu_top[0][0] if npu_top else ""])
                log.flush()
            if child:
                history["CPU"].append(cpu)
                history["GPU"].append(gpu["util"] if gpu else 0.0)
                history["NPU"].append(npu["util"] if npu else 0.0)
                history["child NPU"].append((npu or {}).get("procs", {}).get(child.pid, 0.0))
            print("\033[H\033[J" + render(cpu, gpu, npu), flush=True)
            if args.once or (child and child.poll() is not None):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if log:
            log.close()
        q.close()

    if child:
        child.wait()
        print(f"\n`{' '.join(cmd)}` exited with code {child.returncode} after {len(history['CPU'])} samples:")
        for name, values in history.items():
            s = summarize(values)
            print(f"  {name:<10} peak {s['peak']:5.1f}%   avg {s['avg']:5.1f}%   >=50% busy {s['busy']:4.0%} of the time")
        if summarize(history["child NPU"])["peak"] < 1:
            print("  -> this command never used the NPU itself (check its device setting, e.g. OpenVINO 'NPU').")
        return child.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
