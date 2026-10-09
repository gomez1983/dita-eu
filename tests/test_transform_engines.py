"""Voice Transform regressions. All network and SDK calls are mocked."""

import contextlib
import io
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

import transcriber


class GroqTransformTests(unittest.TestCase):
    def setUp(self):
        self.post_patch = patch("transcriber.requests.post")
        self.post = self.post_patch.start()
        self.addCleanup(self.post_patch.stop)
        self.engine = transcriber.GroqTranscriber(api_key="test-key")

    @staticmethod
    def response(payload, status=200):
        return Mock(status_code=status, json=Mock(return_value=payload), text="private error body")

    def test_transcribes_audio_then_transforms_with_exact_specification_prompt(self):
        audio_seen = []

        def respond(url, **kwargs):
            if url.endswith("audio/transcriptions"):
                audio_seen.append(kwargs["files"]["file"][1].read())
                return self.response({"text": "  Deixe formal.  "})
            return self.response({"choices": [{"message": {"content": "Resultado\n\nSegundo parágrafo."}}]})

        self.post.side_effect = respond
        original = "Olá!\n\nSegunda parte."
        with patch("builtins.open", side_effect=AssertionError("Audio/text must stay in RAM")):
            result = self.engine.transform_text(original, b"wave audio")

        self.assertEqual(result, "Resultado\n\nSegundo parágrafo.")
        self.assertEqual(audio_seen, [b"wave audio"])
        self.assertEqual(self.post.call_count, 2)
        first, second = self.post.call_args_list
        self.assertEqual(first.kwargs["data"]["model"], "whisper-large-v3-turbo")
        self.assertEqual(second.kwargs["json"]["model"], "llama-3.3-70b-versatile")
        self.assertEqual(second.kwargs["json"]["messages"], [
            {"role": "system", "content": transcriber.TRANSFORM_SYSTEM_PROMPT},
            {"role": "user", "content": f"[TEXTO_ORIGINAL]\n{original}\n\n[COMANDO_DE_VOZ]\nDeixe formal."}
        ])
        for call in self.post.call_args_list:
            self.assertGreater(call.kwargs["timeout"], 0)
            self.assertLessEqual(call.kwargs["timeout"], 6)

    def test_system_prompt_is_identical_to_the_feature_document(self):
        spec = (Path(__file__).resolve().parents[1] / "FEATURE_VOICE_TRANSFORM.md").read_text(encoding="utf-8")
        prompt = spec.split("## 4.", 1)[1].split("```text\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(transcriber.TRANSFORM_SYSTEM_PROMPT, prompt)

    def test_silence_cancels_without_calling_transformation(self):
        for instruction in ("", " \n ", None):
            with self.subTest(instruction=instruction):
                self.post.reset_mock()
                self.post.return_value = self.response({"text": instruction})
                self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
                self.post.assert_called_once()

    def test_empty_inputs_or_missing_key_do_not_make_requests(self):
        for text, audio in (("", b"audio"), (" \n", b"audio"), ("Original", b"")):
            self.assertEqual(self.engine.transform_text(text, audio), "")
        self.engine.api_key = ""
        self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
        self.post.assert_not_called()

    def test_failed_transcription_does_not_send_selection_to_llm_or_log_body(self):
        self.post.return_value = self.response({}, status=503)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.engine.transform_text("private selection", b"private audio"), "")
        self.post.assert_called_once()
        self.assertNotIn("private", output.getvalue())

    def test_failed_or_empty_transformation_never_returns_original_or_instruction(self):
        for response in (
            self.response({}, status=500),
            self.response({"choices": []}),
            self.response({"choices": [{"message": {"content": None}}]}),
            self.response({"choices": [{"message": {"content": " \n "}}]}),
        ):
            with self.subTest(response=response):
                self.post.side_effect = [self.response({"text": "make formal"}), response]
                self.assertEqual(self.engine.transform_text("Original", b"audio"), "")

    def test_network_error_does_not_log_private_exception_details(self):
        self.post.side_effect = RuntimeError("private selection and audio")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
        self.assertNotIn("private", output.getvalue())


class GeminiTransformTests(unittest.TestCase):
    def setUp(self):
        self.client_patch = patch("transcriber.genai.Client")
        self.client_factory = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.engine = transcriber.GeminiTranscriber(api_key="test-key", model="legacy-dictation-model")
        self.generate = self.client_factory.return_value.models.generate_content

    def test_two_sdk_calls_use_inline_audio_then_exact_transform_prompt(self):
        self.generate.side_effect = [Mock(text="  Resuma em tópicos.  "), Mock(text="- Primeiro\n- Segundo")]
        original = "Primeiro parágrafo.\n\nSegundo parágrafo."
        with patch("builtins.open", side_effect=AssertionError("Audio/text must stay in RAM")):
            self.assertEqual(self.engine.transform_text(original, b"wave audio"), "- Primeiro\n- Segundo")

        first, second = self.generate.call_args_list
        self.assertEqual(first.kwargs["contents"][0].inline_data.data, b"wave audio")
        self.assertEqual(first.kwargs["contents"][0].inline_data.mime_type, "audio/wav")
        self.assertEqual(second.kwargs["contents"], [
            f"[TEXTO_ORIGINAL]\n{original}\n\n[COMANDO_DE_VOZ]\nResuma em tópicos."
        ])
        self.assertEqual(second.kwargs["config"].system_instruction, transcriber.TRANSFORM_SYSTEM_PROMPT)
        for call in self.generate.call_args_list:
            self.assertEqual(call.kwargs["model"], "gemini-flash-lite-latest")
            self.assertGreater(call.kwargs["config"].http_options.timeout, 0)
            self.assertLessEqual(call.kwargs["config"].http_options.timeout, 6000)
        self.assertEqual(self.engine.model, "legacy-dictation-model")

    def test_silence_stops_after_instruction_transcription(self):
        for instruction in (None, "", " \n "):
            with self.subTest(instruction=instruction):
                self.generate.reset_mock()
                self.generate.return_value = Mock(text=instruction)
                self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
                self.generate.assert_called_once()

    def test_missing_inputs_or_client_do_not_make_requests(self):
        for text, audio in (("", b"audio"), (" \n", b"audio"), ("Original", b"")):
            self.assertEqual(self.engine.transform_text(text, audio), "")
        self.engine.client = None
        self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
        self.generate.assert_not_called()

    def test_empty_response_does_not_replace_with_original_or_instruction(self):
        self.generate.side_effect = [Mock(text="Resuma"), Mock(text=None)]
        self.assertEqual(self.engine.transform_text("Original", b"audio"), "")

    def test_sdk_error_does_not_log_private_exception_details(self):
        self.generate.side_effect = RuntimeError("private selection and audio")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
        self.assertNotIn("private", output.getvalue())

    def test_timeout_returns_promptly_and_never_starts_late_transformation(self):
        release = threading.Event()
        executors = []
        real_executor = transcriber.concurrent.futures.ThreadPoolExecutor

        def make_executor(*args, **kwargs):
            executor = real_executor(*args, **kwargs)
            executors.append(executor)
            return executor

        def blocked_transcription(**kwargs):
            release.wait(2)
            return Mock(text="Resuma")

        self.generate.side_effect = blocked_transcription
        try:
            with patch.object(transcriber, "TRANSFORM_TIMEOUT_SECONDS", 0.05), \
                    patch("transcriber.concurrent.futures.ThreadPoolExecutor", side_effect=make_executor), \
                    contextlib.redirect_stdout(io.StringIO()):
                started = time.monotonic()
                self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 0.75, "Timed-out calls must not wait for executor shutdown")
        finally:
            release.set()
            for executor in executors:
                executor.shutdown(wait=True)
        self.generate.assert_called_once()


class EngineRoutingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = transcriber.TranscriptionEngine.__new__(transcriber.TranscriptionEngine)
        self.engine.groq_engine = Mock(api_key="groq-key")
        self.engine.gemini_engine = Mock(client=Mock())

    def test_transform_uses_only_active_provider_even_on_failure(self):
        for provider, other in (("groq", "gemini"), ("gemini", "groq")):
            for result in ("Resultado", ""):
                with self.subTest(provider=provider, result=result):
                    self.engine.engine_type = provider
                    active = getattr(self.engine, f"{provider}_engine")
                    inactive = getattr(self.engine, f"{other}_engine")
                    active.reset_mock()
                    inactive.reset_mock()
                    active.transform_text.return_value = result
                    self.assertEqual(self.engine.transform_text("Original", b"audio"), result)
                    active.transform_text.assert_called_once_with("Original", b"audio")
                    inactive.assert_not_called()
                    self.assertEqual(inactive.method_calls, [])

    def test_unknown_provider_does_not_send_to_any_provider(self):
        self.engine.engine_type = "unknown"
        self.assertEqual(self.engine.transform_text("Original", b"audio"), "")
        self.assertEqual(self.engine.groq_engine.method_calls, [])
        self.assertEqual(self.engine.gemini_engine.method_calls, [])

    def test_normal_dictation_still_falls_back_and_preserves_raw_text(self):
        self.engine.engine_type = "groq"
        self.engine.groq_engine.transcribe.return_value = ""
        self.engine.gemini_engine.transcribe.return_value = "Ditado original"
        self.engine.groq_engine.translate_text.return_value = ""
        self.engine.gemini_engine.translate_text.return_value = ""
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.engine.transcribe(b"dictation", "en"), "Ditado original")
        self.engine.groq_engine.transcribe.assert_called_once_with(b"dictation")
        self.engine.gemini_engine.transcribe.assert_called_once_with(b"dictation")
        self.engine.groq_engine.translate_text.assert_called_once_with("Ditado original", "en")
        self.engine.gemini_engine.translate_text.assert_called_once_with("Ditado original", "en")

    def test_original_dictation_still_skips_translation(self):
        self.engine.engine_type = "gemini"
        self.engine.gemini_engine.transcribe.return_value = "Texto ditado"
        self.assertEqual(self.engine.transcribe(b"dictation"), "Texto ditado")
        self.engine.groq_engine.translate_text.assert_not_called()
        self.engine.gemini_engine.translate_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
