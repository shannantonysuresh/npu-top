# npu-top

**See if your AI work is actually running on the NPU.** Live CPU / GPU / NPU usage in the terminal on Windows,
with the one thing Task Manager won't tell you: **which process is using the NPU**. Zero dependencies.

```
npu-top 0.1.0   22:06:11   (Ctrl+C to quit)

  CPU  ███████████░░░░░░░░░░░░░░░░░░░  37.1%
  GPU  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░   6.6%
  NPU  ██████████████████████████████ 100.0%

  NPU by process:
    python.exe                   pid 21624   100.0%

  GPU by process:
    WindowsTerminal.exe          pid 18988     6.1%
```
*Real capture: an OpenVINO model running on an Intel Core Ultra 5 115U's AI Boost NPU.*

## Why

On new "AI PC" laptops it is surprisingly hard to tell whether a model really runs on the NPU or silently falls
back to the CPU or GPU. The Task Manager NPU graph is easy to miss, has no per-process breakdown, and can't be
logged or scripted.

## Install

```bash
pip install git+https://github.com/shannantonysuresh/npu-top
```

## Use

```bash
npu-top                                  # live view, refreshes every second
npu-top --log usage.csv                  # also append every sample to a CSV
npu-top -- python infer.py               # run a command, then report its usage
npu-top --once                           # one sample (for scripts)
```

`npu-top -- <command>` answers "did my script use the NPU?" with numbers:

```
`python npu_load.py 15` exited with code 0 after 66 samples:
  CPU        peak 100.0%   avg  65.5%   >=50% busy  53% of the time
  GPU        peak 100.0%   avg  26.5%   >=50% busy  23% of the time
  NPU        peak 100.0%   avg  22.6%   >=50% busy  23% of the time
  child NPU  peak 100.0%   avg  22.6%   >=50% busy  23% of the time
```
`child NPU` counts only the process you launched, so other apps can't make a run look NPU-accelerated.
If it stays at 0, npu-top tells you the command never touched the NPU.

## How it works

Windows publishes per-process, per-engine usage for every GPU-class adapter as `GPU Engine` performance counters.
NPUs (via Microsoft's compute driver model) appear there as adapters with a **`Neural`** engine. npu-top reads those
counters through `pdh.dll` with plain `ctypes`, then aggregates them the way Task Manager does: an engine's usage is
the sum over processes, and an adapter's usage is its busiest engine. CPU is `% Processor Utility`, the same
number Task Manager shows.

## Compatibility

| | Status |
|---|---|
| Intel AI Boost (Core Ultra) | Tested (driver 32.0.100.5540, Windows 11) |
| AMD Ryzen AI, Qualcomm Hexagon | Should work if the driver reports a `Neural` engine; untested, reports welcome |
| Linux / macOS | Not supported (Windows performance counters only) |

If the NPU shows "not found", your NPU driver isn't publishing usage counters. Update the driver.

## Development

```bash
pip install -e ".[test]"
pytest -q          # aggregation logic is pure Python and tested without Windows
```

MIT licensed.
