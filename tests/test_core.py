from npu_top.core import aggregate, by_kind, parse_instance, summarize

NPU = "luid_0x00000000_0x065FC259_phys_0"
GPU = "luid_0x00000000_0x0000FD3E_phys_0"


def inst(pid, luid, eng, engtype):
    return f"pid_{pid}_{luid}_eng_{eng}_engtype_{engtype}"


def test_parse_instance():
    assert parse_instance(inst(4812, NPU, 3, "Neural")) == (4812, "0x00000000_0x065fc259_0", 3, "neural")
    assert parse_instance(inst(9, GPU, 0, "Video Decode")) [3] == "video decode"
    assert parse_instance("_Total") is None


def test_aggregate_classifies_and_sums_like_task_manager():
    samples = {
        inst(100, NPU, 0, "Neural"): 60.0,   # two processes share the NPU engine -> engine at 90%
        inst(200, NPU, 0, "Neural"): 30.0,
        inst(100, GPU, 0, "3D"): 20.0,       # GPU: busiest engine wins (compute 45 > 3D 20+5)
        inst(300, GPU, 0, "3D"): 5.0,
        inst(300, GPU, 1, "Compute"): 45.0,
        "garbage": 99.0,
    }
    ad = aggregate(samples)
    npu, gpu = by_kind(ad, "NPU"), by_kind(ad, "GPU")
    assert npu["util"] == 90.0 and npu["procs"] == {100: 60.0, 200: 30.0}
    assert gpu["util"] == 45.0 and gpu["procs"] == {100: 20.0, 300: 45.0}


def test_aggregate_caps_and_handles_missing():
    ad = aggregate({inst(1, NPU, 0, "Neural"): 70.0, inst(2, NPU, 0, "Neural"): 60.0})
    assert by_kind(ad, "NPU")["util"] == 100.0  # rounding across processes can exceed 100
    assert by_kind(ad, "GPU") is None
    assert aggregate({}) == {}


def test_summarize():
    s = summarize([0, 50, 100, 10])
    assert s == {"peak": 100, "avg": 40, "busy": 0.5}
    assert summarize([]) == {"peak": 0.0, "avg": 0.0, "busy": 0.0}
