"""Small ffmpeg / ffprobe helpers."""
import json, shutil, subprocess

class FFError(RuntimeError): pass

def have_ffmpeg(): return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

def run(args, cwd=None, timeout=1800):
    """Run ffmpeg with args (list, without the 'ffmpeg'). Returns stderr text. Raises FFError with the tail of stderr."""
    if not have_ffmpeg(): raise FFError("ffmpeg/ffprobe not found - install ffmpeg (https://ffmpeg.org/download.html) and retry")
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *map(str, args)], cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    if p.returncode: raise FFError("ffmpeg failed: " + p.stderr[-1500:])
    return p.stderr

def probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode: raise FFError(f"ffprobe could not read {path}: {p.stderr[-300:]}")
    return json.loads(p.stdout)

def duration(path):
    d = probe(path); f = d.get("format", {}).get("duration")
    if f: return float(f)
    return max(float(s.get("duration", 0) or 0) for s in d.get("streams", [{}]))

def vstream(path):
    return next((s for s in probe(path)["streams"] if s.get("codec_type") == "video"), None)

def has_filter(name):
    if not have_ffmpeg(): return False
    p = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return any(l.split()[1:2] == [name] for l in p.stdout.splitlines() if len(l.split()) > 1)
