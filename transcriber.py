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

    def translate_to_english(self, audio_bytes: bytes) -> str:
        """Tradução direta de áudio para Inglês via Groq Whisper (~300ms)"""
        if not audio_bytes or not self.api_key:
            return ""

        url = "https://api.groq.com/openai/v1/audio/translations"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")
        }
        # Nota: Groq requer modelo whisper-large-v3 para endpoint /translations
        data = {
            "model": "whisper-large-v3",
            "response_format": "json",
            "temperature": "0.0",
            "prompt": "Translate into natural, conversational, everyday spoken English as used by native speakers in daily chats. Keep natural colloquial phrasing, contractions, and authentic tone without being overly formal or robotic."
        }

        try:
            response = requests.post(url, headers=headers, files=files, data=data, timeout=8)
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "").strip()
            else:
                print(f"[GroqTranscriber Translation] Erro {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            print(f"[GroqTranscriber Translation] Erro na requisição: {e}")
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

    def translate(self, audio_bytes: bytes, target_lang: str) -> str:
        """Tradução multimodal direta com estrita coloquialidade humana nativa"""
        if not audio_bytes or not self.client:
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
            f"Você é um tradutor de fala de altíssima fidelidade e naturalidade coloquial humana.\n"
            f"Sua tarefa é ouvir o áudio fornecido e traduzi-lo DIRETAMENTE para o idioma de destino: {target_name}.\n\n"
            "Diretrizes Rígidas de Tradução:\n"
            "1. Coloquialidade e Fluência Nativa: Mantenha rigorosamente o tom natural, casual e coloquial da fala humana falada no dia a dia. Quem ler o texto deve ter a sensação nítida de que foi digitado espontaneamente por uma pessoa nativa naquele idioma (como numa conversa amigável de chat ou trabalho informal).\n"
            "2. Proibido Soar Robótico: Não soe como tradutor automático formal, engessado, literal ou com jargões robóticos.\n"
            "3. Fidelidade à Intenção: Não invente palavras rebuscadas, não distorça a intenção original e não adicione pontuações artificiais desnecessárias.\n"
            "4. Retorno Limpo: Retorne EXCLUSIVAMENTE o texto final traduzido. Não adicione introduções, aspas extras, notas explicativas ou comentários.\n"
            "5. Silêncio ou Ruído: Se o áudio for inaudível, vazio ou ruído estático, retorne exatamente uma string vazia."
        )

        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type="audio/wav"
        )

        prompt = f"Traduza este áudio diretamente para {target_name} respeitando estritamente a naturalidade coloquial humana."

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[audio_part, prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            text = response.text or ""
            return text.strip()
        except Exception as e:
            print(f"[GeminiTranscriber Translation] Erro na chamada Gemini: {e}")
            return ""


class TranscriptionEngine:
    """Fachada unificada que direciona para Groq ou Gemini conforme configuração e idioma"""
    def __init__(self, engine_type: str = "groq", groq_api_key: str = "", gemini_api_key: str = "", gemini_model: str = "gemini-flash-latest"):
        self.engine_type = engine_type.lower()
        self.groq_engine = GroqTranscriber(api_key=groq_api_key)
        self.gemini_engine = GeminiTranscriber(api_key=gemini_api_key, model=gemini_model)

    def transcribe(self, audio_bytes: bytes, target_lang: str = "original") -> str:
        target_lang = (target_lang or "original").lower()

        # 1. Modo Normal (Transcrição Original sem tradução)
        if target_lang in ("original", "none", ""):
            if self.engine_type == "groq":
                text = self.groq_engine.transcribe(audio_bytes)
                if not text and self.gemini_engine.client:
                    print("[TranscriptionEngine] Groq sem resposta, tentando fallback no Gemini...")
                    text = self.gemini_engine.transcribe(audio_bytes)
                return text
            else:
                return self.gemini_engine.transcribe(audio_bytes)

        # 2. Modo Tradução para Inglês (en): Prioriza endpoint de tradução nativo da Groq (~300ms)
        if target_lang == "en":
            if self.engine_type == "groq" and self.groq_engine.api_key:
                text = self.groq_engine.translate_to_english(audio_bytes)
                if text:
                    return text
                print("[TranscriptionEngine] Groq translation falhou ou vazia, tentando fallback no Gemini...")
            
            # Fallback transparente no Gemini Flash
            return self.gemini_engine.translate(audio_bytes, "en")

        # 3. Demais idiomas (es, fr, de, it): Google Gemini Flash com diretriz coloquial
        return self.gemini_engine.translate(audio_bytes, target_lang)
