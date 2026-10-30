import json
import os
import winreg
import sys

def get_base_dir() -> str:
    """Retorna o diretório base onde o aplicativo reside (mesmo congelado com PyInstaller)."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(os.path.join(exe_dir, "config.json")) or os.path.exists(os.path.join(exe_dir, ".env")):
            return exe_dir
        parent_dir = os.path.dirname(exe_dir)
        if os.path.exists(os.path.join(parent_dir, "config.json")) or os.path.exists(os.path.join(parent_dir, ".env")):
            return parent_dir
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")

PRESET_PROMPTS = {
    "dota": (
        "Reescreva a mensagem com a personalidade caricata e impaciente de um jogador de Dota 2 altamente estressado: "
        "use termos técnicos do jogo (TF, BKB, ward, Rosh, tilt, sem dedo, farmar jungle), caixa alta para ênfase de revolta, "
        "sarcasmo agressivo e indignação com o posicionamento dos aliados, sem usar filtros ou formalidade."
    ),
    "pirata": (
        "Reescreva o texto como um pirata beberrão em alto-mar: use jargões navais (marujo, prancha, rum, sete mares, "
        "tempestade, canhões), entonação rústica, exclamativa e ameaçadora de forma bem humorada."
    ),
    "adolescente": (
        "Reescreva o texto no tom caricato, hiperbólico e histérico de uma adolescente obcecada fofocando com a melhor amiga (bestie): "
        "use MUITAS PALAVRAS EM CAIXA ALTA para choque ou ênfase dramática, gírias atuais (tipo 'juro', 'literalmente morri', 'miga', "
        "'divou', 'surreal', 'que ódiooo', 'mano do céu', 'passando mal'), repetição exagerada de vogais, emoticons e emojis caricatos "
        "(😭, 💀, 💅, ✨, 👁️👄👁️, 🤡), mantendo um humor teatral irresistível."
    ),
    "corporativo": (
        "Reescreva o texto no padrão corporativo executivo de alto escalão: linguagem polida, impessoal, assertiva, "
        "orientada a resultados e alinhamento estratégico, sem gírias ou informalidades."
    ),
    "email_prytter": (
        "Reescreva mantendo as informações, mas deixe de forma coloquial, sem gírias e amistosa. "
        "Não use jargões nem emojis. Tom amistoso, sempre como se fosse uma troca de emails entre cliente "
        "e prestador de serviço com bastante intimidade. Substituir \"movie\" por \"Moove\", pois é o nome da empresa. "
        "Não precisa de saudação nem encerramento. Modificar informações que possam ser ofensivas ou atribuir falsas informações pessoais."
    ),
    "coach_quantico": (
        "Reescreva o texto no tom insuportável e pedante de um coach quântico de prosperidade: encare qualquer frase "
        "como um bloqueio energético ou oportunidade de saltar para a quinta dimensão. Use jargões caricatos "
        "('reprogramação celular', 'frequência em Hertz', 'mindset de abundância', 'ressonância', 'cocriação no vácuo'), "
        "gratidão forçada e imperativos para a pessoa 'virar a chave'."
    ),
    "tiozao_churrasco": (
        "Reescreva a mensagem com a personalidade inconfundível do tiozão do churrasco de domingo: use piadas ruins de "
        "duplo sentido, trocadilhos infames (estilo 'é pavê ou pacumê'), referências a carro velho pegando no tranco, "
        "cerveja gelada e conselhos caseiros duvidosos. Trate o interlocutor como 'campeão', 'fera', 'chefe' ou 'meu patrão'."
    ),
    "trailer_cinema": (
        "Reescreva o texto como o narrador de trailer de filme de ação épico dos anos 90: comece obrigatoriamente com a "
        "fórmula 'Em um mundo onde...' ou equivalente dramático. Narre qualquer acontecimento trivial como uma catástrofe global "
        "iminente, repleta de explosões mentais, contagens regressivas cruciais e destinos selados, em tom solene, grave e cinematográfico."
    ),
    "livre": ""
}

DEFAULT_CONFIG = {
    "engine": "groq",  # "groq" ou "gemini"
    "groq_api_key": os.getenv("GROQ_API_KEY", ""),
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "gemini_model": "gemini-flash-lite-latest",
    "trigger_keys": ["f8"],
    "transform_trigger_keys": ["shift+f8"],
    "microphone_index": None,
    "hud_bottom_offset": 350,
    "theme": "dark",
    "autostart": False,
    "local_model_size": "base",  # modelo do motor offline: "base" ou "small"
    "translation_target": "original",  # "original", "en", "es", "fr", "de", "it", "custom"
    "custom_preset": "email_prytter",
    "custom_prompt": PRESET_PROMPTS["email_prytter"],
    "custom_prompts": {}
}

def get_preset_prompt(config: dict, preset_key: str) -> str:
    """Retorna o prompt para o preset informado, respeitando edições customizadas salvas pelo usuário."""
    if not preset_key:
        return ""
    custom_map = config.get("custom_prompts", {})
    if preset_key in custom_map:
        return custom_map[preset_key]
    if preset_key == "livre":
        return config.get("custom_prompt", "")
    return PRESET_PROMPTS.get(preset_key, "")


def load_config() -> dict:
    if os.path.exists(ENV_FILE):
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE, override=False)
        except Exception:
            pass

    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config.update(data)
        except Exception as e:
            print(f"[Config] Erro ao ler config.json: {e}")
    else:
        save_config(config)

    # Garante que chaves de API sejam carregadas do .env caso não estejam no config.json
    if not config.get("groq_api_key"):
        config["groq_api_key"] = os.getenv("GROQ_API_KEY", "")
    if not config.get("gemini_api_key"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")

    # Migra modelo para gemini-flash-lite-latest caso esteja no gemini-flash-latest esgotado
    if config.get("gemini_model") in ("gemini-flash-latest", "gemini-3.8-flash", "", None):
        config["gemini_model"] = "gemini-flash-lite-latest"

    # Sincroniza dinamicamente com o Registro real do Windows para evitar discrepancias
    config["autostart"] = is_windows_autostart_enabled()

    return config

def save_config(config: dict):
    # Proteção: preserva chaves de API caso o config recebido venha com chave em branco
    if not config.get("groq_api_key") and os.getenv("GROQ_API_KEY"):
        config["groq_api_key"] = os.getenv("GROQ_API_KEY")
    if not config.get("gemini_api_key") and os.getenv("GEMINI_API_KEY"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY")

    if config.get("gemini_model") in ("gemini-flash-latest", "gemini-3.8-flash", "", None):
        config["gemini_model"] = "gemini-flash-lite-latest"

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Erro ao salvar config.json: {e}")

def is_windows_autostart_enabled() -> bool:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DitaEu"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False

def set_windows_autostart(enable: bool, app_path: str = None):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DitaEu"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            if not app_path:
                app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}" --background')
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Config] Erro ao configurar inicializacao com Windows: {e}")
