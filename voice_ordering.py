"""
MVP speech-to-text for a voice ordering system.

Three modes:
    python mvp_stt.py mic                  record from mic, transcribe, print
    python mvp_stt.py file audio.wav       transcribe an existing wav
    python mvp_stt.py eval data/           run WER eval over a labelled folder

Setup:
    pip install faster-whisper sounddevice soundfile numpy jiwer

The eval folder needs a refs.csv with two columns: filename,reference
and the matching .wav files alongside it.
"""

import csv
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
MODEL_SIZE = "small"  # try "base" if too slow, "medium" if accuracy is short

# The single most important knob in this whole script. Whisper conditions its
# decoding on this text, so listing your catalogue terms makes it far more
# likely to produce them instead of a phonetically similar common word.
# Keep it under ~200 tokens; longer prompts start to hurt.
CATALOGUE_PROMPT = (
    "Grocery order. Products: Milo, Horlicks, kaya, Meiji fresh milk, "
    "Marigold milk powder, Jasmine rice, Nissin instant noodles, Yeo's "
    "chrysanthemum tea, Khong Guan biscuits, Panadol, Sustagen, wholemeal "
    "bread, kang kong, bee hoon, tau huay."
)

_model = None


def get_model():
    global _model
    if _model is None:
        # int8 keeps this usable on a laptop CPU. Use device="cuda",
        # compute_type="float16" if you have a GPU.
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(wav_path, use_prompt=True):
    """Return (text, mean_logprob). mean_logprob is a rough confidence proxy:
    closer to 0 is more confident, below about -1.0 is usually garbage."""
    segments, _info = get_model().transcribe(
        str(wav_path),
        language="en",
        beam_size=5,
        vad_filter=True,
        # Elderly speakers pause mid-sentence. The default 500ms endpoint
        # chops them off, so give it a much longer tail.
        vad_parameters={"min_silence_duration_ms": 2000},
        initial_prompt=CATALOGUE_PROMPT if use_prompt else None,
    )
    segments = list(segments)
    if not segments:
        return "", -99.0
    text = " ".join(s.text.strip() for s in segments)
    conf = sum(s.avg_logprob for s in segments) / len(segments)
    return text.strip(), conf


def record(out_path="recording.wav"):
    """Press Enter to start, Enter again to stop. Deliberately dumb:
    push-to-talk is what you want in the real UI anyway."""
    import sounddevice as sd

    input("Press Enter to start recording...")
    chunks = []
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    stream.start()

    def pump():
        while not stop:
            data, _ = stream.read(1024)
            chunks.append(data.copy())

    import threading

    stop = False
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    input("Recording. Press Enter to stop...")
    stop = True
    t.join(timeout=1.0)
    stream.stop()
    stream.close()

    audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((1, 1))
    sf.write(out_path, audio, SAMPLE_RATE)
    return out_path


def normalize(s):
    """Light normalization so WER measures real errors, not punctuation."""
    import re

    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def run_eval(folder):
    """Compare WER with and without catalogue biasing. This is the number
    that tells you whether biasing is worth building on."""
    from jiwer import wer

    folder = Path(folder)
    rows = list(csv.DictReader(open(folder / "refs.csv")))

    refs, hyp_on, hyp_off = [], [], []
    for row in rows:
        wav = folder / row["filename"]
        if not wav.exists():
            print(f"  missing: {wav}")
            continue
        on, conf = transcribe(wav, use_prompt=True)
        off, _ = transcribe(wav, use_prompt=False)
        refs.append(normalize(row["reference"]))
        hyp_on.append(normalize(on))
        hyp_off.append(normalize(off))
        print(f"\n{row['filename']}  (conf {conf:.2f})")
        print(f"  ref      : {row['reference']}")
        print(f"  biased   : {on}")
        print(f"  unbiased : {off}")

    if refs:
        print(f"\n{'=' * 50}")
        print(f"WER with catalogue prompt   : {wer(refs, hyp_on):.3f}")
        print(f"WER without catalogue prompt: {wer(refs, hyp_off):.3f}")
        print(f"n = {len(refs)} utterances")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "mic"

    if mode == "mic":
        path = record()
        text, conf = transcribe(path)
        print(f"\nTranscript: {text}")
        print(f"Confidence: {conf:.2f}")
    elif mode == "file":
        text, conf = transcribe(sys.argv[2])
        print(f"\nTranscript: {text}")
        print(f"Confidence: {conf:.2f}")
    elif mode == "eval":
        run_eval(sys.argv[2])
    else:
        print(__doc__)