"""Transcrição local offline via faster-whisper (CTranslate2).

Os pesos dos modelos não são embutidos no executável: são baixados sob demanda
para %APPDATA%/Dita-eu/models/<tamanho>/ na primeira vez que o usuário ativa o
motor local. O áudio é processado 100% em memória e nunca vai para o disco.
"""
import io
import os
import threading
import wave

import numpy as np

# Tamanhos oferecidos ao usuário (tamanho aproximado do download, em MB).
MODEL_SIZES = {
    "base": 145,
    "small": 480,
}
DEFAULT_MODEL_SIZE = "base"


def get_models_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Dita-eu", "models")


def get_model_path(model_size: str) -> str:
    return os.path.join(get_models_dir(), model_size)


def is_model_downloaded(model_size: str) -> bool:
    """Um modelo só é considerado pronto se o arquivo de pesos existir."""
    return os.path.isfile(os.path.join(get_model_path(model_size), "model.bin"))


def is_available() -> bool:
    """Indica se a biblioteca faster-whisper está presente neste build."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def download_model(model_size: str) -> str:
    """Baixa os pesos do modelo (bloqueante). Deve rodar fora da thread da UI."""
    from faster_whisper import download_model as _download
    target = get_model_path(model_size)
    os.makedirs(target, exist_ok=True)
    return _download(model_size, output_dir=target)


def _wav_to_float32(audio_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        channels = wav.getnchannels()
        width = wav.getsampwidth()
    if width != 2:
        raise ValueError("Somente WAV PCM de 16 bits é suportado")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


class LocalTranscriber:
    """Transcritor offline. O modelo é carregado uma única vez e reaproveitado."""

    def __init__(self, model_size: str = DEFAULT_MODEL_SIZE, language: str = "pt"):
        self.model_size = model_size if model_size in MODEL_SIZES else DEFAULT_MODEL_SIZE
        self.language = language
        self._model = None
        self._device = "cpu"
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return is_available() and is_model_downloaded(self.model_size)

    def _load(self, force_cpu: bool = False):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel
        device, compute_type = "cpu", "int8"
        if not force_cpu:
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    device, compute_type = "cuda", "float16"
            except Exception:
                pass
        try:
            self._model = WhisperModel(get_model_path(self.model_size),
                                       device=device, compute_type=compute_type)
        except Exception:
            if device == "cpu":
                raise
            # GPU presente, mas sem cuDNN/CUDA utilizável: cai para CPU.
            device = "cpu"
            self._model = WhisperModel(get_model_path(self.model_size),
                                       device="cpu", compute_type="int8")
        self._device = device
        return self._model

    def _run(self, model, audio):
        segments, _info = model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            initial_prompt="Transcreva em português do Brasil com pontuação correta e sem hesitações.",
        )
        # O gerador é lazy: erros de CUDA só afloram ao consumi-lo.
        return " ".join(seg.text.strip() for seg in segments).strip()

    def preload(self):
        """Carrega o modelo antecipadamente para o primeiro ditado não ter atraso."""
        if not self.ready:
            return
        try:
            with self._lock:
                self._load()
        except Exception as e:
            print(f"[LocalTranscriber] Falha ao pré-carregar o modelo: {type(e).__name__}")

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes or not self.ready:
            return ""
        try:
            audio = _wav_to_float32(audio_bytes)
            with self._lock:
                model = self._load()
                try:
                    return self._run(model, audio)
                except Exception:
                    if self._device == "cpu":
                        raise
                    # CUDA falhou na inferência (ex.: DLL do cuBLAS ausente): refaz na CPU.
                    self._model = None
                    return self._run(self._load(force_cpu=True), audio)
        except Exception as e:
            # Não registra o conteúdo do áudio nem do texto.
            print(f"[LocalTranscriber] Erro na transcrição local: {type(e).__name__}")
            return ""
