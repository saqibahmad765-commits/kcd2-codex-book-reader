"""Offline KCD2 speech worker. Persistent CPU model; bounded, cancellable playback."""
import argparse
import base64
from collections import deque
import json
from pathlib import Path
import re
import sys
import threading
import time
import wave

import numpy as np
import onnxruntime as ort
from piper import PiperVoice, PiperConfig, SynthesisConfig

ROOT = Path(__file__).resolve().parent
VOICE = "Piper Cori"
output_lock = threading.Lock()


def report(*items):
    with output_lock:
        print("\t".join(map(str, items)), flush=True)


def load_voice():
    settings = ort.SessionOptions()
    settings.intra_op_num_threads = 2
    settings.inter_op_num_threads = 1
    settings.add_session_config_entry("session.intra_op.allow_spinning", "0")
    settings.add_session_config_entry("session.inter_op.allow_spinning", "0")
    profile = json.loads((ROOT / "voice-config.json").read_text(encoding="utf-8"))
    model = (ROOT / profile["model"]).resolve()
    if not model.is_relative_to((ROOT / "voices").resolve()):
        raise ValueError("Voice model must be inside the package voices folder")
    session = ort.InferenceSession(str(model), sess_options=settings,
                                  providers=["CPUExecutionProvider"])
    config = PiperConfig.from_dict(json.loads(
        model.with_suffix(".onnx.json").read_text(encoding="utf-8")))
    return PiperVoice(session, config)


def sections(text):
    # Bound each inference call, including long text without sentence punctuation.
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        words = sentence.split()
        chunk = ""
        for word in words:
            if len(chunk) + len(word) > 260 and chunk:
                yield chunk
                chunk = ""
            # Break pathological tokens without dropping their content.
            while len(word) > 260:
                if chunk:
                    yield chunk
                    chunk = ""
                yield word[:260]
                word = word[260:]
            chunk = (chunk + " " + word).strip()
        if chunk:
            yield chunk


class Worker:
    def __init__(self, voice):
        self.voice = voice
        self.cv = threading.Condition()
        self.buffers = deque()
        self.offset = 0
        self.generation = -1
        self.active = None
        self.request = None
        self.paused = False
        self.finished = False
        self.started = False
        self.played = 0
        self.quitting = False
        self.producer = threading.Thread(target=self.generate, daemon=True)
        self.producer.start()

    def cancel_locked(self):
        old = self.active
        self.active = None
        self.request = None
        self.buffers.clear()
        self.offset = 0
        self.paused = False
        self.finished = False
        if old is not None:
            report("DONE", old, "cancelled")
        self.cv.notify_all()

    def generate(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.quitting or self.request is not None)
                if self.quitting:
                    return
                serial, text, volume, rate = self.request
                self.request = None
            try:
                config = SynthesisConfig(volume=volume / 100,
                                         length_scale=1 / (1.10 ** rate))
                for section in sections(text):
                    with self.cv:
                        if self.active != serial or self.quitting:
                            break
                        self.cv.wait_for(lambda: self.active != serial or self.quitting
                                         or (not self.paused and len(self.buffers) < 2))
                        if self.active != serial or self.quitting:
                            break
                    for chunk in self.voice.synthesize(section, config):
                        audio = np.asarray(chunk.audio_float_array, dtype=np.float32)
                        with self.cv:
                            self.cv.wait_for(lambda: self.active != serial or self.quitting
                                             or (not self.paused and len(self.buffers) < 2))
                            if self.active != serial or self.quitting:
                                break
                            self.buffers.append(audio)
                with self.cv:
                    if self.active == serial:
                        self.finished = True
            except Exception as exc:
                with self.cv:
                    if self.active == serial:
                        report("ERROR", "synthesis", type(exc).__name__, str(exc))
                        self.buffers.clear()
                        self.active = None
                        report("DONE", serial, "error")

    def callback(self, outdata, frames, time_info=None, status=None):
        outdata.fill(0)
        with self.cv:
            if self.active is None or self.paused:
                return
            written = 0
            while self.buffers and written < frames:
                if not self.started:
                    self.started = True
                    report("START", self.active)
                audio = self.buffers[0]
                take = min(frames - written, len(audio) - self.offset)
                outdata[written:written + take, 0] = audio[self.offset:self.offset + take]
                written += take
                self.offset += take
                self.played += take
                if self.offset == len(audio):
                    self.buffers.popleft()
                    self.offset = 0
                    self.cv.notify_all()
            if self.finished and not self.buffers:
                report("DONE", self.active, "complete")
                self.active = None

    def command(self, line):
        parts = line.rstrip("\r\n").split("\t")
        with self.cv:
            if parts[0] == "QUIT":
                self.cancel_locked()
                self.quitting = True
                self.cv.notify_all()
                return False
            if parts[0] == "STATUS":
                report("STATUS", self.active, self.played, self.paused, len(self.buffers))
                return True
            serial = int(parts[1])
            if parts[0] == "STOP" and len(parts) == 2:
                if serial < self.generation:
                    report("IGNORED", serial)
                else:
                    self.generation = serial
                    self.cancel_locked()
                    report("STOPPED", serial)
            elif parts[0] in ("PAUSE", "RESUME") and len(parts) == 2:
                if serial != self.active:
                    report("IGNORED", serial)
                else:
                    self.paused = parts[0] == "PAUSE"
                    report("PAUSED" if self.paused else "RESUMED", serial)
                    self.cv.notify_all()
            elif parts[0] == "SPEAK" and len(parts) in (5, 6):
                if serial <= self.generation:
                    report("IGNORED", serial)
                    return True
                text = base64.b64decode(parts[4], validate=True).decode("utf-8")
                if not text.strip() or len(text) > 20000:
                    raise ValueError("Invalid text length")
                if len(parts) == 6 and base64.b64decode(parts[5]).decode() != VOICE:
                    raise ValueError("Voice unavailable")
                volume = max(0, min(100, int(parts[2])))
                rate = max(-10, min(10, int(parts[3])))
                self.cancel_locked()
                self.generation = serial
                self.active = serial
                self.started = False
                self.played = 0
                self.request = (serial, text, volume, rate)
                report("ACCEPTED", serial, "voice=" + VOICE)
                self.cv.notify_all()
            else:
                raise ValueError("Invalid command")
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--null-audio", action="store_true")
    parser.add_argument("--wave-test", type=Path)
    args = parser.parse_args()
    start = time.perf_counter()
    voice = load_voice()
    if args.wave_test:
        with wave.open(str(args.wave_test), "wb") as wav:
            voice.synthesize_wav(
                "This is Cori, your local Kingdom Come reader. "
                "Open the Codex or a supported book to begin.", wav)
        report("WAVE_OK", args.wave_test)
        return
    worker = Worker(voice)
    stream = None
    stopped = threading.Event()
    if args.null_audio:
        def pump():
            audio = np.zeros((512, 1), dtype=np.float32)
            while not stopped.wait(512 / voice.config.sample_rate):
                worker.callback(audio, 512)
        threading.Thread(target=pump, daemon=True).start()
    else:
        import sounddevice as sd
        stream = sd.OutputStream(samplerate=voice.config.sample_rate, channels=1,
                                 dtype="float32", blocksize=512, latency="low",
                                 callback=worker.callback)
        stream.start()
    report("READY", VOICE, "load_ms=" + str(round((time.perf_counter() - start) * 1000)))
    try:
        for line in sys.stdin:
            try:
                if not worker.command(line):
                    break
            except Exception as exc:
                report("ERROR", "protocol", type(exc).__name__, str(exc))
    finally:
        worker.command("QUIT")
        stopped.set()
        if stream is not None:
            stream.abort()
            stream.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report("FATAL", type(exc).__name__, str(exc))
        sys.exit(1)
