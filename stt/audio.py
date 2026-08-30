"""Browser audio -> 16 kHz mono WAV.

Phones do not hand you a clean WAV. Chrome's MediaRecorder emits WebM/Opus and
Safari emits MP4/AAC, neither of which libsndfile reads. So there are two
supported routes and the frontend can pick either:

  1. Upload WAV directly (encode with the Web Audio API in the browser). No
     server dependency at all — preferred, and the reason this is not simply
     "install ffmpeg".
  2. Upload the raw MediaRecorder blob. Needs ffmpeg on the server; we detect
     it once and give an actionable error rather than a stack trace if absent.

Both ASR engine families want 16 kHz mono, matching SAMPLE_RATE in
voice_ordering.py.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16000

# Below this, faster-whisper reliably hallucinates speech out of silence, and
# no engine can produce anything useful. Reject early with a clear signal.
MIN_DURATION_S = 0.35
MAX_DURATION_S = 60.0

_FFMPEG = shutil.which("ffmpeg")


class AudioError(ValueError):
    """Audio we cannot turn into something an engine can read."""


def ffmpeg_available() -> bool:
    return _FFMPEG is not None


def _decode_with_soundfile(path: Path) -> tuple[np.ndarray, int]:
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return data, rate


def _decode_with_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    if not _FFMPEG:
        raise AudioError(
            f"cannot decode {path.suffix or 'this audio'}: libsndfile does not "
            "support it and ffmpeg is not installed. Either install ffmpeg on "
            "the server, or have the frontend upload 16kHz mono WAV (see "
            "README_stt.md)."
        )
    out = path.with_suffix(".converted.wav")
    result = subprocess.run(
        [_FFMPEG, "-nostdin", "-y", "-i", str(path),
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", str(out)],
        capture_output=True,
    )
    if result.returncode != 0 or not out.exists():
        tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AudioError("ffmpeg failed to decode audio: " + " | ".join(tail))
    return _decode_with_soundfile(out)


def to_wav16k_mono(source: str | Path, dest: str | Path | None = None) -> Path:
    """Normalise any supported audio file to 16 kHz mono WAV.

    Returns the path to the converted file (which may be `source` itself if it
    already conforms). Raises AudioError with actionable text on bad input.
    """
    source = Path(source)
    if not source.exists():
        raise AudioError(f"no such audio file: {source}")

    try:
        data, rate = _decode_with_soundfile(source)
    except Exception:
        data, rate = _decode_with_ffmpeg(source)

    if data.size == 0:
        raise AudioError("audio contains no samples")

    # Mixdown to mono. Averaging channels rather than taking channel 0 keeps
    # the signal if a phone records into only the second channel.
    if data.ndim == 2 and data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    mono = data.reshape(-1)

    duration = len(mono) / rate
    if duration < MIN_DURATION_S:
        raise AudioError(
            f"audio is only {duration:.2f}s; need at least {MIN_DURATION_S}s "
            "(too short to contain speech, and models hallucinate on silence)"
        )
    if duration > MAX_DURATION_S:
        mono = mono[: int(MAX_DURATION_S * rate)]

    if rate != SAMPLE_RATE:
        mono = _resample(mono, rate, SAMPLE_RATE)

    dest = Path(dest) if dest else Path(
        tempfile.mkstemp(suffix=".wav", prefix="stt_")[1]
    )
    sf.write(str(dest), mono, SAMPLE_RATE, subtype="PCM_16")
    return dest


def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear resample.

    Deliberately dependency-free. Speech at 16 kHz from a phone mic does not
    justify pulling in scipy or librosa, and the engines' own front-ends are
    tolerant. Swap for soxr if measurement ever shows this hurting WER.
    """
    if src_rate == dst_rate:
        return samples
    duration = len(samples) / src_rate
    target_len = int(duration * dst_rate)
    if target_len <= 1:
        raise AudioError("audio too short to resample")
    src_idx = np.linspace(0, len(samples) - 1, num=target_len)
    return np.interp(src_idx, np.arange(len(samples)), samples).astype("float32")


def duration_seconds(path: str | Path) -> float:
    info = sf.info(str(path))
    return info.frames / info.samplerate
