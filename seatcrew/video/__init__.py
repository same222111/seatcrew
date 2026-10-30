"""SeatCrew video toolkit: storyboard format, pluggable TTS / visuals backends, an ffmpeg editor and an automated
quality check. Used by the short_video example workflow and by `seatcrew video ...` (CLI).

Quality policy: real backends (ElevenLabs / OpenAI TTS / edge-tts neural voices, AI images or video clips, or your
own clips) produce final output. The offline path (flite/silent voice, generated title cards) is a DRAFT PREVIEW:
it is labeled in the UI, burned into the video and in the file name, and must never be presented as final quality."""
from .storyboard import load_storyboard, validate_storyboard, SIZES, CAMERAS, TRANSITIONS
from .templates import TEMPLATES

DRAFT_LABEL = "DRAFT PREVIEW - NOT FINAL QUALITY"
KEY_ENVS = {"openai": "OPENAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "replicate": "REPLICATE_API_TOKEN", "stability": "STABILITY_API_KEY"}

def key_status():
    """Booleans only - key values are never read into config, logs or the UI."""
    import os
    return {k: bool(os.getenv(v)) for k, v in KEY_ENVS.items()}
