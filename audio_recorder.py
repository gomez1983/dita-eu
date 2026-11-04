import io
import threading
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from runtime_diagnostics import logger

MAX_RECORDING_SECONDS = 300

class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index: int = None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.is_recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._generation = 0
        self._sample_count = 0
        self.current_volume = 0.0

    def _audio_callback(self, indata, frames, time_info, status, generation=None):
        with self._lock:
            if (not self.is_recording
                    or (generation is not None and generation != self._generation)):
                return
            remaining = self.sample_rate * MAX_RECORDING_SECONDS - self._sample_count
            if remaining <= 0:
                return
            audio_copy = indata[:remaining].copy()
            self._frames.append(audio_copy)
            self._sample_count += len(audio_copy)
            if len(audio_copy):
                rms = np.sqrt(np.mean(audio_copy**2))
                self.current_volume = float(rms)

    def start(self):
        # Native calls can block; serialize them outside the frame/callback lock.
        with self._lifecycle_lock:
            if self._stream is not None:
                raise RuntimeError("A recording stream is already open")
            with self._lock:
                self._frames = []
                self._sample_count = 0
                self._generation += 1
                generation = self._generation
                self.is_recording = True
                self.current_volume = 0.0
            stream = None
            try:
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    device=self.device_index,
                    dtype="float32",
                    callback=lambda *args: self._audio_callback(*args, generation=generation),
                )
                stream.start()
                self._stream = stream
            except Exception as error:
                with self._lock:
                    self.is_recording = False
                    self._generation += 1
                    self._frames = []
                    self.current_volume = 0.0
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                logger.warning("Microphone start failed type=%s", type(error).__name__)
                raise

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
        with self._lifecycle_lock:
            with self._lock:
                self.is_recording = False
                self._generation += 1
                stream, self._stream = self._stream, None
                captured, self._frames = self._frames, []
                self.current_volume = 0.0
            if stream is not None:
                try:
                    stream.stop()
                except Exception as error:
                    logger.warning("Microphone stop failed type=%s", type(error).__name__)
                finally:
                    try:
                        stream.close()
                    except Exception as error:
                        logger.warning("Microphone close failed type=%s", type(error).__name__)

        if not captured:
            return b""
        audio_data = np.concatenate(captured, axis=0)

        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        
        buffer = io.BytesIO()
        wavfile.write(buffer, self.sample_rate, audio_int16)
        buffer.seek(0)
        return buffer.read()
