import json
import os
import winreg
import sys

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "engine": "groq",  # "groq" ou "gemini"
    "groq_api_key": os.getenv("GROQ_API_KEY", ""),
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "gemini_model": "gemini-flash-latest",
    "trigger_keys": ["f8"],
    "microphone_index": None,
    "hud_bottom_offset": 350,
    "theme": "dark",
    "autostart": False,
    "translation_target": "original"  # "original", "en", "es", "fr", "de", "it"
}

def load_config() -> dict:
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

    return config

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Erro ao salvar config.json: {e}")

def set_windows_autostart(enable: bool, app_path: str = None):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DitaEu"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            if not app_path:
                app_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Config] Erro ao configurar inicializacao com Windows: {e}")
