"""Disposable speech/download worker. Native libraries never enter the GUI process."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import unicodedata
from urllib.request import urlopen
import wave
from language_lens.runtime import recovery_instruction

from language_lens.services.voices import (
    MAX_TEXT_LENGTH, Voice, voice_runtime_ready, valid_file, verified_model, voice_by_id,
)


def emit(**event) -> None:
    print(json.dumps(event, ensure_ascii=True), flush=True)


def download(voice: Voice, root: Path, scratch: Path, progress=emit) -> None:
    directory = root / voice.id
    directory.mkdir(parents=True, exist_ok=True)
    completed = 0
    for name, size, checksum in voice.files:
        target = directory / name
        progress(stage="checking", done=completed, total=voice.total_bytes)
        if valid_file(target, size, checksum):
            completed += size
            progress(done=completed, total=voice.total_bytes)
            continue
        # Scratch is on the same volume as the destination, so publication is atomic.
        temporary = scratch / (name + ".part")
        try:
            progress(stage="downloading", done=completed, total=voice.total_bytes)
            with urlopen(voice.url(name), timeout=30) as response, temporary.open("wb") as output:
                count = 0
                while chunk := response.read(256 * 1024):
                    count += len(chunk)
                    if count > size:
                        raise ValueError("The downloaded voice file has an unexpected size.")
                    output.write(chunk)
                    progress(done=completed + count, total=voice.total_bytes)
            progress(stage="verifying", done=completed + count, total=voice.total_bytes)
            if not valid_file(temporary, size, checksum):
                raise ValueError("Voice verification failed. Please retry the download.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        completed += size
        progress(done=completed, total=voice.total_bytes)


def validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Select between 1 and {MAX_TEXT_LENGTH:,} characters to read aloud.")
    if any(unicodedata.category(c) == "Cs" or
           (unicodedata.category(c) == "Cc" and c not in "\n\r\t") for c in text):
        raise ValueError("The selected text contains invalid Unicode or unsupported control characters.")
    return unicodedata.normalize("NFC", text)


def synthesize(voice: Voice, root: Path, text: str, output: Path,
               phonemes: list[str] | None = None, *, speed: float = 1.0) -> None:
    if type(speed) not in (int, float) or not .5 <= speed <= 1.5 or not math.isfinite(speed):
        raise ValueError("Invalid speech speed.")
    if phonemes is None:
        text = validate_text(text)
    else:
        if (not isinstance(phonemes, list) or not phonemes
                or any(not isinstance(part, str) for part in phonemes)
                or not 0 < sum(map(len, phonemes)) <= 16000):
            raise ValueError("Invalid prepared pronunciation.")
    if not voice_runtime_ready(voice):
        raise RuntimeError("Speech components are missing. Download the pronunciation pack in Settings." if voice.phoneme_type == "japanese"
                           else "Speech components need updating. " + recovery_instruction())
    if voice.phoneme_type == "japanese":
        from language_lens.services.language_packs import activate
        activate("ja-speech")
    model = verified_model(voice, root)
    import numpy as np
    import onnxruntime
    from piper.config import PiperConfig
    from piper.phonemize_espeak import EspeakPhonemizer
    from piper.voice import PiperVoice

    config = PiperConfig.from_dict(json.loads(model.with_suffix(".onnx.json").read_text(encoding="utf-8")))
    config.length_scale /= speed
    if (config.espeak_voice != voice.espeak or config.phoneme_type.value != voice.phoneme_type
            or config.vowel_clusters):
        raise ValueError("This voice does not match its expected accent and speech format.")
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = onnxruntime.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    renderer = PiperVoice(session=session, config=config)
    # Bypass Piper's [[raw phonemes]] text parser: OCR is always plain text.
    if phonemes is not None:
        sentences = [list(part) for part in phonemes]
    elif voice.phoneme_type == "japanese":
        from piper.phonemize_japanese import JapanesePhonemizer
        sentences = JapanesePhonemizer().phonemize(text)
    else:
        sentences = EspeakPhonemizer().phonemize(voice.espeak, text)
    audible = False
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(config.sample_rate)
        for phones in sentences:
            if not any(p not in " \t\r\n.,:;!?-" for p in phones):
                continue
            missing = set(phones) - config.phoneme_id_map.keys()
            if missing:
                raise ValueError("This voice cannot pronounce part of the selected text.")
            audio = np.asarray(renderer.phoneme_ids_to_audio(renderer.phonemes_to_ids(phones))).reshape(-1)
            if not audio.size or not np.isfinite(audio).all():
                raise ValueError("The voice returned invalid audio. Try again with a shorter selection.")
            peak = float(np.max(np.abs(audio)))
            audible |= peak >= 1e-6
            pcm = (np.clip(audio / max(1.0, peak), -1, 1) * 32767).astype("<i2")
            handle.writeframes(pcm.tobytes())
    if not audible:
        raise ValueError("No pronounceable text was found in this selection.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("download", "download-pronunciation", "synthesize", "pronunciation", "phonemes"))
    parser.add_argument("--voice", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    try:
        from language_lens.services.diagnostics import initialize
        initialize(f"speech-{args.command}")
        voice = voice_by_id(args.voice)
        if args.command in ("download", "download-pronunciation"):
            if voice.phoneme_type == "japanese":
                from language_lens.services.language_packs import install
                install("ja-speech", lambda _message: emit(stage="verifying"),
                        lambda item: emit(stage="downloading", done=item.received, total=item.total))
            if args.command == "download":
                download(voice, args.root, args.scratch)
        else:
            from language_lens.services.offline import no_network
            with no_network():
                request = json.loads(sys.stdin.buffer.read(160000).decode("utf-8"))
                if args.command == "pronunciation":
                    from language_lens.services.pronunciation import Pronouncer, prepare_japanese
                    # Validate without discarding the original Unicode source offsets.
                    validate_text(request["text"])
                    prepared = (prepare_japanese(request["text"], request["spans"])
                                if voice.phoneme_type == "japanese" else
                                Pronouncer().prepare_for_spans(request["text"], voice.locale, request["spans"]))
                    result = prepared.to_dict()
                    result["voice_id"] = voice.id
                    (args.scratch / "pronunciation.json").write_text(
                        json.dumps(result, ensure_ascii=False), encoding="utf-8"
                    )
                else:
                    synthesize(voice, args.root, request["text"], args.scratch / "selection.wav",
                               request["phonemes"] if args.command == "phonemes" else None,
                               speed=request.get("speed", 1.0))
        emit(ok=True)
        return 0
    except Exception as exc:
        from language_lens.services.diagnostics import record_failure
        record_failure(f"speech-{args.command}", exc)
        from language_lens.services.errors import KnownTaskError, MESSAGES
        emit(error=MESSAGES.get(exc.code, str(exc)) if isinstance(exc, KnownTaskError) else str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
