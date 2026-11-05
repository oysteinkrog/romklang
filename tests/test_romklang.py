"""Tests for the DSP and state handling. Run: python3 -m pytest tests"""

import importlib.machinery
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile as wavfile

SCRIPT = Path(__file__).resolve().parent.parent / "romklang"


@pytest.fixture
def rk(tmp_path, monkeypatch):
    monkeypatch.setenv("ROMKLANG_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("ROMKLANG_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    loader = importlib.machinery.SourceFileLoader("romklang", str(SCRIPT))
    spec = importlib.util.spec_from_loader("romklang", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    (tmp_path / "data/hrir").mkdir(parents=True)
    return mod


def write_hrir(rk, name, data, rate=48000):
    wavfile.write(rk.DATA / "hrir" / f"{name}.wav", rate, data.astype(np.float32))


def test_min_phase_fir_follows_target(rk):
    pts = [(20, 0.0), (1000, 0.0), (3000, 6.0), (10000, -6.0), (20000, -6.0)]
    h = rk.min_phase_fir(pts, 48000)
    freqs = np.fft.rfftfreq(1 << 16, 1 / 48000)
    mag = 20 * np.log10(np.abs(np.fft.rfft(h, 1 << 16)) + 1e-12)
    for f, want in [(100, 0.0), (3000, 6.0), (10000, -6.0)]:
        got = mag[np.argmin(np.abs(freqs - f))]
        assert abs(got - want) < 0.5, (f, got, want)
    # Minimum phase: almost all energy at the start.
    e = np.cumsum(h**2) / np.sum(h**2)
    assert e[len(h) // 20] > 0.99


def test_parse_graphic_eq_sorts_and_validates(rk):
    pts = rk.parse_graphic_eq("Preamp: -3 dB\nGraphicEQ: 1000 1; 20 -2; 1000 3")
    assert pts == [(20.0, -2.0), (1000.0, 3.0)]
    with pytest.raises(SystemExit):
        rk.parse_graphic_eq("GraphicEQ: -5 1; 20 2")
    with pytest.raises(SystemExit):
        rk.parse_graphic_eq("GraphicEQ: 20 nan")
    with pytest.raises(SystemExit):
        rk.parse_graphic_eq("no eq here")


def test_read_wav_scales_integer_formats(rk, tmp_path):
    p = tmp_path / "u8.wav"
    wavfile.write(p, 48000, np.array([0, 128, 255], dtype=np.uint8))
    _, d = rk.read_wav(p)
    assert np.allclose(d[:, 0], [-1.0, 0.0, 127 / 128])
    p = tmp_path / "s16.wav"
    wavfile.write(p, 48000, np.array([-32768, 0, 16384], dtype=np.int16))
    _, d = rk.read_wav(p)
    assert np.allclose(d[:, 0], [-1.0, 0.0, 0.5])


def test_14_channel_routing_without_upmix(rk):
    n = 64
    d = np.zeros((n, 14))
    for col, (spk, ear) in enumerate(rk.LAYOUT14):
        if spk == "FL" and ear == "L":
            d[0, col] = 1.0  # FL to left ear: impulse at 0
        if spk == "FR" and ear == "L":
            d[3, col] = 0.5  # FR to left ear: crossfeed at 3
        if spk == "FR" and ear == "R":
            d[0, col] = 1.0
    write_hrir(rk, "test", d)
    st = dict(rk.BASE_STATE, hrir="test", upmix="off")
    ir = rk.build_ir(st, 48000)
    # Columns: LtoL, LtoR, RtoL, RtoR. Left ear worst case is 1 + 0.5 = 1.5.
    assert ir[0, 0] == pytest.approx(1 / 1.5, rel=1e-4)
    assert ir[3, 2] == pytest.approx(0.5 / 1.5, rel=1e-4)
    assert ir[0, 3] == pytest.approx(1 / 1.5, rel=1e-4)
    assert np.allclose(ir[:, 1], 0)


def test_7_channel_mirrors_left_to_right(rk):
    rng = np.random.default_rng(1)
    d = rng.normal(size=(128, 7)) * np.exp(-np.arange(128) / 20)[:, None]
    write_hrir(rk, "seven", d)
    st = dict(rk.BASE_STATE, hrir="seven", upmix="on")
    ir = rk.build_ir(st, 48000)
    # Symmetric head: left input to left ear equals right input to right ear.
    assert np.allclose(ir[:, 0], ir[:, 3], atol=1e-6)
    assert np.allclose(ir[:, 1], ir[:, 2], atol=1e-6)


def test_gain_scales_level(rk):
    d = np.zeros((16, 14))
    d[0, :] = 1.0
    write_hrir(rk, "flat", d)
    base = rk.build_ir(dict(rk.BASE_STATE, hrir="flat"), 48000)
    loud = rk.build_ir(dict(rk.BASE_STATE, hrir="flat", gain_db=6.0), 48000)
    assert np.abs(loud).max() / np.abs(base).max() == pytest.approx(
        10 ** (6 / 20), rel=1e-4
    )


def test_44100_resample_keeps_level(rk):
    d = np.zeros((256, 14))
    d[0, :] = 1.0
    write_hrir(rk, "r48", d)
    a = rk.build_ir(dict(rk.BASE_STATE, hrir="r48"), 48000)
    b = rk.build_ir(dict(rk.BASE_STATE, hrir="r48"), 44100)
    ga = np.abs(np.fft.rfft(a[:, 0], 4096))[:10].mean()
    gb = np.abs(np.fft.rfft(b[:, 0], 4096))[:10].mean()
    assert ga == pytest.approx(gb, rel=0.02)


def test_defaults_stay_live_for_keys_the_user_did_not_set(rk):
    rk.CONF_DIR.mkdir(parents=True)
    rk.DEFAULTS.write_text(json.dumps({"output": "dac-a", "gain_db": 3}))
    rk.save_user_state({"hrir": "x"})
    rk.DEFAULTS.write_text(json.dumps({"output": "dac-b", "gain_db": 3}))
    st = rk.load_state()
    assert st["output"] == "dac-b"
    assert st["hrir"] == "x"


def test_state_rejects_own_node_as_output(rk):
    with pytest.raises(SystemExit):
        rk.check_state(dict(rk.BASE_STATE, output=rk.NODE_IN))


def test_pw_conf_quotes_strings(rk):
    conf = rk.pw_conf(dict(rk.BASE_STATE, output='odd "name"'))
    assert 'target.object  = "odd \\"name\\""' in conf
    with pytest.raises(SystemExit):
        rk.pw_conf(dict(rk.BASE_STATE, output=""))


def test_render_skips_when_current(rk):
    d = np.zeros((16, 14))
    d[0, :] = 1.0
    write_hrir(rk, "dht-", d)
    st: dict = dict(rk.BASE_STATE, output="dac")
    assert rk.render(st, if_stale=True) is True
    assert rk.render(st, if_stale=True) is False
    st["gain_db"] = -3.0
    assert rk.render(st, if_stale=True) is True
