# microphone_record.py
from __future__ import annotations
import queue, math
from dataclasses import dataclass
from typing import Optional
import numpy as np
import sounddevice as sd

try:
    import soundfile as sf
    _SF = True
except Exception:
    _SF = False

def _resample_linear(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x
    ratio = sr_out / sr_in
    n_out = int(round(x.size * ratio))
    xp = np.linspace(0, 1, x.size, endpoint=False)
    xq = np.linspace(0, 1, n_out, endpoint=False)
    y = np.interp(xq, xp, x.astype(np.float32))
    return y.astype(x.dtype)

@dataclass
class MicConfig:
    desired_rate: int = 16000          # what your STT expects
    blocksize: int = 1024
    channels: int = 1
    dtype: str = "int16"
    device: Optional[int] = None       # input device index (from sd.query_devices())
    print_levels: bool = True          # print RMS meter while recording
    save_wav: bool = True              # write last buffer to last_capture.wav for debugging

class MicrophoneRecorder:
    """Robust recorder that negotiates samplerate and returns 16k int16 mono."""
    def __init__(self, cfg: MicConfig = MicConfig()):
        self.cfg = cfg
        self._q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._sr_in = cfg.desired_rate

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._q.put(indata.copy())

    def _open_stream(self):
        # Probe device samplerate if none is specified or desired rate fails
        sr = self.cfg.desired_rate
        try:
            sd.check_input_settings(
                device=self.cfg.device, samplerate=sr,
                channels=self.cfg.channels, dtype=self.cfg.dtype
            )
        except Exception as e:
            print(f"[MIC] {sr} Hz not supported on this device. Will try device default. ({e})")
            info = sd.query_devices(self.cfg.device, kind='input')
            sr = int(info.get('default_samplerate') or 16000)
            print(f"[MIC] Using device default samplerate: {sr} Hz")

        self._sr_in = sr
        self._stream = sd.InputStream(
            samplerate=sr,
            channels=self.cfg.channels,
            dtype=self.cfg.dtype,
            blocksize=self.cfg.blocksize,
            callback=self._callback,
            device=self.cfg.device,
        )
        self._stream.start()
        print(f"[MIC] Stream opened: device={self.cfg.device} sr_in={self._sr_in} -> out=16000")

    def start(self):
        if self._stream is None:
            self._open_stream()
        self._recording = True
        print("[MIC] Recording... (hold-to-talk active)")

    def stop(self) -> np.ndarray:
        self._recording = False
        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get())
        if not chunks:
            print("[MIC] No audio captured.")
            return np.zeros((0,), dtype=np.int16)
        audio = np.concatenate(chunks, axis=0).flatten()

        # Resample to 16k if needed
        if self._sr_in != 16000:
            audio = _resample_linear(audio, self._sr_in, 16000)

        # Normalize dtype to int16
        if audio.dtype != np.int16:
            # input may be int16 already; if float, scale
            if audio.dtype.kind == 'f':
                audio = np.clip(audio, -1.0, 1.0)
                audio = (audio * 32767.0).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        if _SF and self.cfg.save_wav:
            try:
                sf.write("last_capture.wav", audio, 16000, subtype="PCM_16")
                print("[MIC] Saved last_capture.wav (16k mono)")
            except Exception as e:
                print(f"[MIC] Could not save wav: {e}")

        return audio