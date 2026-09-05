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

import os
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

    if dest:
        dest = Path(dest)
    else:
        fd, dest_name = tempfile.mkstemp(suffix=".wav", prefix="stt_")
        os.close(fd)
        dest = Path(dest_name)
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


def record_until_enter(dest: str | Path, prompt: str = "") -> Path:
    """Record from the mic until the user presses Enter.

    Deliberately NOT a fixed-duration recording. Elderly speakers pause
    mid-sentence and speak more slowly, so a timer truncates them — the exact
    failure this project exists to avoid. voice_ordering.py made the same
    choice for the same reason.

    Push-to-talk is also what the real UI will do, so testing this way matches
    how the system will actually be used.
    """
    import threading

    import sounddevice as sd

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if prompt:
        print(prompt)
    input("Press Enter to START recording...")

    chunks: list = []
    stop = threading.Event()
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()

    def pump():
        while not stop.is_set():
            data, _overflowed = stream.read(1024)
            chunks.append(data.copy())

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    input("Recording... press Enter again when you have FINISHED speaking.")
    stop.set()
    thread.join(timeout=2.0)
    stream.stop()
    stream.close()

    if not chunks:
        raise AudioError("no audio captured - check microphone permissions")
    audio = np.concatenate(chunks, axis=0).reshape(-1)
    sf.write(str(dest), audio, SAMPLE_RATE)
    print(f"Saved {dest}  ({len(audio) / SAMPLE_RATE:.1f}s)")
    return dest
