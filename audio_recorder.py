import io
import threading
import numpy as np
import sounddevice as sd
from scipy.io import wavfile

class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index: int = None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.is_recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self.current_volume = 0.0

    def _audio_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            audio_copy = indata.copy()
            with self._lock:
                self._frames.append(audio_copy)
            rms = np.sqrt(np.mean(audio_copy**2))
            self.current_volume = float(rms)

    def start(self):
        with self._lock:
            self._frames = []
            self.is_recording = True
            self.current_volume = 0.0
        
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            device=self.device_index,
            dtype="float32",
            callback=self._audio_callback
        )
        self._stream.start()

    def get_current_audio_bytes(self) -> bytes:
        """Retorna o áudio acumulado até o momento sem interromper a gravação"""
        with self._lock:
            if not self._frames:
                return b""
            audio_data = np.concatenate(self._frames, axis=0)

        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        buffer = io.BytesIO()
        wavfile.write(buffer, self.sample_rate, audio_int16)
        buffer.seek(0)
        return buffer.read()

    def stop(self) -> bytes:
        self.is_recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            if not self._frames:
                return b""
            audio_data = np.concatenate(self._frames, axis=0)
            self._frames = []

        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        
        buffer = io.BytesIO()
        wavfile.write(buffer, self.sample_rate, audio_int16)
        buffer.seek(0)
        return buffer.read()
