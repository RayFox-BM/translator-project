# microphone_record.py
from __future__ import annotations
import queue
import numpy as np
import sounddevice as sd

class MicrophoneRecorder:
    """Simple 16k mono int16 recorder (start/stop)."""
    def __init__(self, rate: int = 16000, blocksize: int = 1024):
        self.rate = rate
        self.blocksize = blocksize
        self._q = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._recording = False

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._q.put(indata.copy())

    def start(self):
        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=self.rate,
                channels=1,
                dtype="int16",
                blocksize=self.blocksize,
                callback=self._callback,
            )
            self._stream.start()
        self._recording = True

    def stop(self) -> np.ndarray:
        self._recording = False
        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get())
        if not chunks:
            return np.zeros((0,), dtype=np.int16)
        audio = np.concatenate(chunks, axis=0).flatten()
        if audio.dtype != np.int16:
            audio = audio.astype(np.int16)
        return audio