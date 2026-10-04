import io
import os
import requests
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

class GroqTranscriber:
    """Motor ultra-rápido via Groq Whisper (~250-350ms de latência)"""
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


class GeminiTranscriber:
    """Motor multimodal via Google Gemini Flash"""
    def __init__(self, api_key: str = None, model: str = "gemini-flash-latest", language: str = "pt-BR"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
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
            "Você é um transcritor de voz para texto de altíssima precisão e inteligência, idêntico ao assistente de ditado do Antigravity.\n"
            "Sua tarefa é transcrever o áudio fornecido diretamente para o texto final digitado pelo usuário.\n\n"
            "Diretrizes:\n"
            "1. Transcreva o que o usuário disse no idioma detectado (prioritariamente Português do Brasil).\n"
            "2. Pontuação expressiva: Adicione pontuação precisa (, . ? ! ; :) respeitando rigorosamente a entonação, pausas e o sentido das perguntas ou afirmações.\n"
            "3. Limpeza inteligente: Remova hesitações, ruídos vocais ('hã', 'éé', 'hum', 'tipo assim' quando usado como hesitação), gaguejos e repetições involuntárias.\n"
            "4. Não resuma, não responda ao usuário e não adicione explicações ou comentários. Retorne EXCLUSIVAMENTE o texto transcrito e limpo.\n"
            "5. Se o áudio for apenas silêncio, chiado ou inaudível, retorne exatamente uma string vazia."
        )

        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type="audio/wav"
        )

        prompt = "Transcreva este áudio exatamente conforme as instruções de pontuação e limpeza."

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[audio_part, prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )
            text = response.text or ""
            return text.strip()
        except Exception as e:
            print(f"[GeminiTranscriber] Erro na chamada Gemini: {e}")
            return ""


class TranscriptionEngine:
    """Fachada unificada que direciona para Groq ou Gemini conforme configuração"""
    def __init__(self, engine_type: str = "groq", groq_api_key: str = "", gemini_api_key: str = "", gemini_model: str = "gemini-flash-latest"):
        self.engine_type = engine_type.lower()
        self.groq_engine = GroqTranscriber(api_key=groq_api_key)
        self.gemini_engine = GeminiTranscriber(api_key=gemini_api_key, model=gemini_model)

    def transcribe(self, audio_bytes: bytes) -> str:
        if self.engine_type == "groq":
            text = self.groq_engine.transcribe(audio_bytes)
            # Se a Groq falhar por algum motivo, faz fallback transparente para Gemini se configurada
            if not text and self.gemini_engine.client:
                print("[TranscriptionEngine] Groq sem resposta, tentando fallback no Gemini...")
                text = self.gemini_engine.transcribe(audio_bytes)
            return text
        else:
            return self.gemini_engine.transcribe(audio_bytes)
