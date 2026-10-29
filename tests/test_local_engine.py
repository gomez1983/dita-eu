"""Motor de transcrição local offline: sem modelo real, rede ou GPU."""
import io
import os
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

import numpy as np

import local_transcriber
from local_transcriber import LocalTranscriber
from transcriber import TranscriptionEngine


def make_wav(samples=None, rate=16000):
    samples = np.zeros(8000, dtype=np.int16) if samples is None else samples
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


class ModelFilesTests(unittest.TestCase):
    def test_model_ready_only_with_weights_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(local_transcriber, "get_models_dir", return_value=tmp):
            self.assertFalse(local_transcriber.is_model_downloaded("base"))
            os.makedirs(os.path.join(tmp, "base"))
            self.assertFalse(local_transcriber.is_model_downloaded("base"))  # pasta vazia
            open(os.path.join(tmp, "base", "model.bin"), "wb").close()
            self.assertTrue(local_transcriber.is_model_downloaded("base"))

    def test_models_live_under_appdata(self):
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\x\AppData\Roaming"}):
            self.assertEqual(local_transcriber.get_models_dir(),
                             os.path.join(r"C:\Users\x\AppData\Roaming", "Dita-eu", "models"))

    def test_unknown_size_falls_back_to_default(self):
        self.assertEqual(LocalTranscriber(model_size="gigante").model_size,
                         local_transcriber.DEFAULT_MODEL_SIZE)

    def test_wav_is_decoded_to_normalized_float32(self):
        audio = local_transcriber._wav_to_float32(make_wav(np.array([0, 16384, -32768], dtype=np.int16)))
        self.assertEqual(audio.dtype, np.float32)
        np.testing.assert_allclose(audio, [0.0, 0.5, -1.0])


class LocalTranscriberTests(unittest.TestCase):
    def setUp(self):
        self.t = LocalTranscriber("base")
        patcher = patch.object(LocalTranscriber, "ready", new=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_empty_when_model_not_downloaded(self):
        with patch.object(LocalTranscriber, "ready", new=False):
            self.assertEqual(self.t.transcribe(make_wav()), "")

    def test_joins_segments(self):
        seg = lambda s: Mock(text=s)
        model = Mock()
        model.transcribe.return_value = ([seg(" Olá "), seg("mundo. ")], None)
        self.t._model, self.t._device = model, "cpu"
        self.assertEqual(self.t.transcribe(make_wav()), "Olá mundo.")

    def test_gpu_failure_retries_on_cpu(self):
        gpu = Mock()
        gpu.transcribe.side_effect = RuntimeError("Library cublas64_12.dll is not found")
        cpu = Mock()
        cpu.transcribe.return_value = ([Mock(text="ok")], None)
        self.t._model, self.t._device = gpu, "cuda"
        with patch.object(self.t, "_load", side_effect=lambda force_cpu=False: cpu if force_cpu else gpu):
            self.assertEqual(self.t.transcribe(make_wav()), "ok")

    def test_errors_never_leak_audio_or_text(self):
        model = Mock()
        model.transcribe.side_effect = ValueError("SEGREDO")
        self.t._model, self.t._device = model, "cpu"
        with patch("builtins.print") as log:
            self.assertEqual(self.t.transcribe(make_wav()), "")
        self.assertNotIn("SEGREDO", str(log.call_args_list))


class LocalEngineRoutingTests(unittest.TestCase):
    def engine(self, groq="gsk", gemini=""):
        e = TranscriptionEngine(engine_type="local", groq_api_key=groq, gemini_api_key=gemini)
        e.groq_engine = Mock(api_key=groq)
        e.gemini_engine = Mock(client=Mock() if gemini else None)
        e.local_engine = Mock()
        return e

    def test_local_model_transcribes_without_touching_cloud(self):
        e = self.engine()
        e.local_engine.ready = True
        e.local_engine.transcribe.return_value = "texto local"
        self.assertEqual(e.transcribe(b"wav"), "texto local")
        e.groq_engine.transcribe.assert_not_called()
        e.gemini_engine.transcribe.assert_not_called()

    def test_silence_offline_does_not_fall_back_to_cloud(self):
        e = self.engine()
        e.local_engine.ready = True
        e.local_engine.transcribe.return_value = ""
        self.assertEqual(e.transcribe(b"wav"), "")
        e.groq_engine.transcribe.assert_not_called()

    def test_missing_model_falls_back_to_cloud(self):
        e = self.engine()
        e.local_engine.ready = False
        e.groq_engine.transcribe.return_value = "texto nuvem"
        self.assertEqual(e.transcribe(b"wav"), "texto nuvem")
        e.local_engine.transcribe.assert_not_called()

    def test_missing_model_without_keys_returns_empty(self):
        e = self.engine(groq="")
        e.local_engine.ready = False
        self.assertEqual(e.transcribe(b"wav"), "")

    def test_translation_still_uses_cloud_llm(self):
        e = self.engine()
        e.local_engine.ready = True
        e.local_engine.transcribe.return_value = "bom dia"
        e.groq_engine.translate_text.return_value = "good morning"
        self.assertEqual(e.transcribe(b"wav", target_lang="en"), "good morning")

    def test_transform_uses_whichever_cloud_provider_has_a_key(self):
        e = self.engine(groq="gsk")
        e.groq_engine.transform_text.return_value = "g"
        self.assertEqual(e.transform_text("t", b"a"), "g")
        e = self.engine(groq="", gemini="key")
        e.gemini_engine.transform_text.return_value = "m"
        self.assertEqual(e.transform_text("t", b"a"), "m")

    def test_preload_only_for_local_engine(self):
        with patch("transcriber.threading.Thread") as thread:
            TranscriptionEngine(engine_type="groq").preload_local()
            thread.assert_not_called()
            TranscriptionEngine(engine_type="local").preload_local()
            thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()

