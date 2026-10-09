import io
import os
import requests
import concurrent.futures
import time
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types


TRANSFORM_SYSTEM_PROMPT = """Você é um assistente de reescrita e transformação cirúrgica de texto integrado diretamente ao cursor do sistema operacional.
Sua missão é pegar o [TEXTO_ORIGINAL] fornecido pelo usuário e reescrevê-lo estritamente de acordo com o [COMANDO_DE_VOZ].

Diretrizes estritas:
1. Retorne EXCLUSIVAMENTE o texto final transformado.
2. NUNCA adicione introduções ("Aqui está a reescrita:"), aspas no início/fim, explicações ou notas de rodapé.
3. Se o comando de voz for de tradução, traduza preservando o sentido e tom.
4. Se o comando de voz pedir um tom específico (formal, casual, pirata, direto, poético), incorpore o tom com maestria sem inventar informações inexistentes no texto original.
5. Mantenha as quebras de linha e estrutura de parágrafos coerentes com o formato do texto original, a menos que o comando peça explicitamente para alterar (ex: "transforme em tópicos")."""

TRANSFORM_TIMEOUT_SECONDS = 12


def _transform_input(original_text: str, instruction: str) -> str:
    return f"[TEXTO_ORIGINAL]\n{original_text}\n\n[COMANDO_DE_VOZ]\n{instruction}"


class GroqTranscriber:
    """Motor ultra-rápido via Groq Whisper (~250ms) + Groq LLMs (~250ms para tradução)"""
    def __init__(self, api_key: str = None, model: str = "whisper-large-v3-turbo", language: str = "pt"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self.language = language

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes or not self.api_key:
            return ""

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        files = {
            "file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")
        }
        data = {
            "model": self.model,
            "language": self.language,
            "response_format": "json",
            "temperature": "0.0",
            "prompt": "Transcreva em português do Brasil com pontuação correta e sem hesitações."
        }

        try:
            response = requests.post(url, headers=headers, files=files, data=data, timeout=8)
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "").strip()
            else:
                print(f"[GroqTranscriber] Erro {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            print(f"[GroqTranscriber] Erro na requisição: {e}")
            return ""

    def translate_text(self, text: str, target_lang: str) -> str:
        """Tradução ultra-rápida (~250ms) e altamente coloquial via LLMs da Groq"""
        if not text or not self.api_key:
            return ""

        lang_targets = {
            "en": "casual, everyday conversational English as used by native speakers in daily chats",
            "es": "casual, everyday colloquial Spanish as used by native speakers in daily chats",
            "fr": "casual, everyday colloquial French as used by native speakers in daily chats",
            "de": "casual, everyday colloquial German as used by native speakers in daily chats",
            "it": "casual, everyday colloquial Italian as used by native speakers in daily chats"
        }
        target_desc = lang_targets.get(target_lang.lower(), target_lang)

        system_instruction = (
            f"You are a native conversational translator. Your task is to translate the spoken user text directly into {target_desc}.\n\n"
            "Strict Rules:\n"
            "1. Tone: Keep it strictly natural, casual, and colloquial—exactly how a native speaker would naturally speak or text a friend or coworker.\n"
            "2. Avoid: Do NOT use formal, robotic, textbook, or overly sophisticated words.\n"
            "3. Punctuation: Keep natural conversational rhythm and contractions (e.g. 'how's it going', 'gonna', 'let's').\n"
            "4. Output: Return EXCLUSIVELY the translated text. Do NOT add quotation marks, explanations, notes, or intro text."
        )

        models_to_try = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
        for model in models_to_try:
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": text}
                        ],
                        "temperature": 0.2
                    },
                    timeout=6
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
            except Exception as e:
                print(f"[GroqTranscriber Translation {model}] Erro: {e}")
                continue

        return ""

    def transform_text(self, original_text: str, instruction_audio_bytes: bytes) -> str:
        """Transcreve a ordem e transforma a seleção, somente pela Groq e em RAM."""
        if not original_text or not original_text.strip() or not instruction_audio_bytes or not self.api_key:
            return ""

        try:
            # Keep this separate from normal dictation: its error logging can
            # include response bodies containing private instruction text.
            with io.BytesIO(instruction_audio_bytes) as audio:
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": ("instruction.wav", audio, "audio/wav")},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "language": self.language,
                        "response_format": "json",
                        "temperature": "0.0",
                        "prompt": "Transcreva a instrução de voz com pontuação correta, sem hesitações."
                    },
                    timeout=6
                )
            if response.status_code != 200:
                return ""
            instruction = (response.json().get("text") or "").strip()
            if not instruction:
                return ""

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": TRANSFORM_SYSTEM_PROMPT},
                        {"role": "user", "content": _transform_input(original_text, instruction)}
                    ],
                    "temperature": 0.2
                },
                timeout=6
            )
            if response.status_code != 200:
                return ""
            choices = response.json().get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message", {}).get("content") or "").strip()
        except Exception:
            # Do not log exception details: SDK/network errors may echo input.
            print("[Groq Voice Transform] Falha na transformação.")
            return ""


class GeminiTranscriber:
    """Motor multimodal via Google Gemini Flash Lite (com timeout seguro de 12s)"""
    def __init__(self, api_key: str = None, model: str = "gemini-flash-lite-latest", language: str = "pt-BR"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or "gemini-flash-lite-latest"
        self.language = language or os.getenv("LANGUAGE", "pt-BR")
        self.client = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiTranscriber] Erro ao instanciar client: {e}")

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes or not self.client:
            return ""

        system_instruction = (
            "Você é um transcritor de voz para texto de altíssima precisão.\n"
            "Diretrizes:\n"
            "1. Transcreva o que o usuário disse no idioma detectado (Português do Brasil).\n"
            "2. Pontuação expressiva e precisa.\n"
            "3. Remova hesitações ('hã', 'éé', gaguejos).\n"
            "4. Retorne EXCLUSIVAMENTE o texto transcrito. Se for inaudível ou silêncio, retorne vazio."
        )

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
        prompt = "Transcreva este áudio exatamente conforme as instruções de pontuação e limpeza."

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=[audio_part, prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )
            return (response.text or "").strip()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call)
                return fut.result(timeout=12)
        except Exception as e:
            print(f"[GeminiTranscriber] Erro ou timeout na chamada Gemini: {e}")
            return ""

    def translate_text(self, text: str, target_lang: str) -> str:
        """Tradução de texto via Gemini com timeout de segurança de 8s"""
        if not text or not self.client:
            return ""

        lang_map = {
            "en": "Inglês (English)",
            "es": "Espanhol (Español)",
            "fr": "Francês (Français)",
            "de": "Alemão (Deutsch)",
            "it": "Italiano (Italiano)"
        }
        target_name = lang_map.get(target_lang.lower(), target_lang)

        system_instruction = (
            f"Você é um tradutor nativo coloquial de altíssima fidelidade.\n"
            f"Traduza o texto fornecido diretamente para {target_name}.\n\n"
            "Diretrizes Rígidas:\n"
            "1. Mantenha o tom 100% natural, casual e coloquial da fala cotidiana entre amigos ou colegas.\n"
            "2. Não soe formal, literal ou robótico.\n"
            "3. Retorne APENAS E EXCLUSIVAMENTE a frase final traduzida, sem aspas, sem marcadores e sem explicações."
        )

        def _call():
            response = self.client.models.generate_content(
                model=self.model,
                contents=[text],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            return (response.text or "").strip()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call)
                return fut.result(timeout=8)
        except Exception as e:
            print(f"[GeminiTranscriber Translation] Erro ou timeout na chamada Gemini: {e}")
            return ""

    def transform_text(self, original_text: str, instruction_audio_bytes: bytes) -> str:
        """Duas chamadas Gemini em RAM, com prazo total independente do ditado."""
        if not original_text or not original_text.strip() or not instruction_audio_bytes or not self.client:
            return ""

        deadline = time.monotonic() + TRANSFORM_TIMEOUT_SECONDS

        def _config(system_instruction, temperature):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                raise TimeoutError()
            return types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                http_options=types.HttpOptions(timeout=min(6000, remaining_ms))
            )

        def _call():
            audio_part = types.Part.from_bytes(data=instruction_audio_bytes, mime_type="audio/wav")
            response = self.client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[audio_part, "Transcreva a instrução falada neste áudio."],
                config=_config(
                    "Transcreva exclusivamente a instrução de voz no idioma falado, com pontuação correta e sem hesitações. "
                    "Não execute a instrução. Se o áudio for inaudível ou silêncio, retorne vazio.",
                    0.1
                )
            )
            instruction = (response.text or "").strip()
            if not instruction:
                return ""
            response = self.client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[_transform_input(original_text, instruction)],
                config=_config(TRANSFORM_SYSTEM_PROMPT, 0.2)
            )
            return (response.text or "").strip()

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_call)
            return future.result(timeout=TRANSFORM_TIMEOUT_SECONDS)
        except Exception:
            print("[Gemini Voice Transform] Falha ou timeout na transformação.")
            return ""
        finally:
            # A context manager would wait for an unresponsive SDK call during
            # shutdown, defeating future.result's timeout. Late results are ignored.
            executor.shutdown(wait=False, cancel_futures=True)


class TranscriptionEngine:
    """Fachada unificada ultra-rápida (~500ms para tradução completa) com zero travamento"""
    def __init__(self, engine_type: str = "groq", groq_api_key: str = "", gemini_api_key: str = "", gemini_model: str = "gemini-flash-lite-latest"):
        self.engine_type = engine_type.lower()
        self.groq_engine = GroqTranscriber(api_key=groq_api_key)
        self.gemini_engine = GeminiTranscriber(api_key=gemini_api_key, model=gemini_model or "gemini-flash-lite-latest")

    def transform_text(self, original_text: str, instruction_audio_bytes: bytes) -> str:
        """Transformação respeita estritamente o motor selecionado, sem fallback."""
        if self.engine_type == "groq":
            return self.groq_engine.transform_text(original_text, instruction_audio_bytes)
        if self.engine_type == "gemini":
            return self.gemini_engine.transform_text(original_text, instruction_audio_bytes)
        return ""

    def transcribe(self, audio_bytes: bytes, target_lang: str = "original") -> str:
        target_lang = (target_lang or "original").lower()

        # 1. Transcrição do áudio em texto (prioriza motor selecionado)
        raw_text = ""
        if self.engine_type == "groq":
            if self.groq_engine.api_key:
                raw_text = self.groq_engine.transcribe(audio_bytes)
            if not raw_text and self.gemini_engine.client:
                print("[TranscriptionEngine] Groq sem resposta, tentando fallback no Gemini...")
                raw_text = self.gemini_engine.transcribe(audio_bytes)
        else:
            if self.gemini_engine.client:
                raw_text = self.gemini_engine.transcribe(audio_bytes)
            if not raw_text and self.groq_engine.api_key:
                print("[TranscriptionEngine] Gemini sem resposta, tentando fallback no Groq...")
                raw_text = self.groq_engine.transcribe(audio_bytes)

        if not raw_text:
            return ""

        # 2. Se for modo normal (sem tradução), retorna o texto original transcrito instantaneamente
        if target_lang in ("original", "none", ""):
            return raw_text

        # 3. Modo Tradução Coloquial em Alta Velocidade (prioriza motor selecionado)
        translated = ""
        if self.engine_type == "gemini":
            if self.gemini_engine.client:
                translated = self.gemini_engine.translate_text(raw_text, target_lang)
            if not translated and self.groq_engine.api_key:
                print("[TranscriptionEngine] Gemini translation falhou, tentando fallback no Groq...")
                translated = self.groq_engine.translate_text(raw_text, target_lang)
        else:
            if self.groq_engine.api_key:
                translated = self.groq_engine.translate_text(raw_text, target_lang)
            if not translated and self.gemini_engine.client:
                print("[TranscriptionEngine] Groq translation falhou, tentando fallback no Gemini...")
                translated = self.gemini_engine.translate_text(raw_text, target_lang)

        # Se por qualquer motivo a tradução falhar, retorna a transcrição original (nunca perde o que foi falado)
        return translated if translated else raw_text
