"""Optional 3D: image -> GLB model of a character, shown in the in-app 360 viewer (bundled model-viewer, no CDN).

  meshy      POST /openapi/v1/image-to-3d (Meshy-6), poll, download model_urls.glb          MESHY_API_KEY
  tripo      v3: POST /v3/files (upload) -> POST /v3/generation/image-to-model -> /v3/tasks  TRIPO_API_KEY
  replicate  any image-to-3D slug (default firtoz/trellis; tencent/hunyuan3d-2 also works)   REPLICATE_API_TOKEN
  draft      offline: a textured "standee" GLB (front image on a card) - lets you try the viewer; not a real model

Live-test status: mocked HTTP only (tests/test_characters.py)."""
import json, os, struct, time
from pathlib import Path
from . import providers as PV
from .imagegen import _multipart

class _Job:
    name = "3d"; poll_every = 8; max_wait = 1200
    def run(self, image, out, sleep=time.sleep, clock=time.time):
        job = self.submit(image); t0 = clock()
        while clock() - t0 < self.max_wait:
            u = self.poll(job)
            if u:
                data, _ = PV.req("GET", u, {}, timeout=600, what=f"{self.name} download")
                if len(data) < 100 or data[:4] != b"glTF": raise PV.ProviderError(f"{self.name}: downloaded file is not a GLB")
                Path(out).write_bytes(data); return Path(out)
            sleep(self.poll_every)
        raise PV.ProviderError(f"{self.name}: timed out")

class Meshy(_Job):
    name = "meshy"; base = "https://api.meshy.ai/openapi/v1"
    def h(self): return {"Authorization": f"Bearer {PV.need('MESHY_API_KEY')}"}
    def submit(self, image):
        d = PV.jreq("POST", f"{self.base}/image-to-3d", self.h(), dict(image_url=PV.data_uri(image), target_formats=["glb"], should_texture=True), what="meshy")
        return d.get("result") or d.get("id")
    def poll(self, job):
        d = PV.jreq("GET", f"{self.base}/image-to-3d/{job}", self.h(), what="meshy"); s = d.get("status")
        if s in ("FAILED", "CANCELED", "EXPIRED"): raise PV.ProviderError(f"meshy: {(d.get('task_error') or {}).get('message') or s}")
        return (d.get("model_urls") or {}).get("glb") if s == "SUCCEEDED" else None

class Tripo(_Job):
    name = "tripo"; base = "https://openapi.tripo3d.ai/v3"
    def h(self): return {"Authorization": f"Bearer {PV.need('TRIPO_API_KEY')}"}
    def submit(self, image):
        data, ct = _multipart({}, [("file", image)])
        up = json.loads(PV.req("POST", f"{self.base}/files", dict(self.h(), **{"Content-Type": ct}), data=data, what="tripo upload")[0])
        tok = (up.get("data") or {}).get("file_token")
        if not tok: raise PV.ProviderError(f"tripo upload: {up.get('message') or 'no file_token'}")
        d = PV.jreq("POST", f"{self.base}/generation/image-to-model", self.h(), dict(input=tok), what="tripo")
        if d.get("code", 0) != 0: raise PV.ProviderError(f"tripo: {d.get('message')}")
        return (d.get("data") or {}).get("task_id")
    def poll(self, job):
        d = (PV.jreq("GET", f"{self.base}/tasks/{job}", self.h(), what="tripo").get("data") or {}); s = str(d.get("status", "")).lower()
        if s in ("failed", "cancelled", "banned", "expired"): raise PV.ProviderError(f"tripo: {s}")
        if s == "success":
            o = d.get("output") or {}; u = o.get("pbr_model") or o.get("model")
            if not u: raise PV.ProviderError("tripo: no model url")
            return u
        return None

class Replicate3D(_Job):
    name = "replicate"; default_model = "firtoz/trellis"
    def __init__(self, model=None): self.model = model or os.getenv("SEATCREW_3D_MODEL") or self.default_model
    def h(self): return {"Authorization": f"Bearer {PV.need('REPLICATE_API_TOKEN')}"}
    def submit(self, image):
        uri = PV.data_uri(image); inp = dict(images=[uri], generate_model=True, texture_size=1024) if "trellis" in self.model else dict(image=uri)
        if ":" in self.model: return PV.jreq("POST", "https://api.replicate.com/v1/predictions", self.h(), dict(version=self.model.split(":", 1)[1], input=inp), what="replicate 3d")
        return PV.jreq("POST", f"https://api.replicate.com/v1/models/{self.model}/predictions", self.h(), dict(input=inp), what="replicate 3d")
    def poll(self, job):
        j = PV.jreq("GET", job["urls"]["get"], self.h(), what="replicate 3d")
        if j["status"] in ("failed", "canceled"): raise PV.ProviderError(f"replicate 3d: {j.get('error') or j['status']}")
        if j["status"] != "succeeded": return None
        o = j["output"]
        if isinstance(o, dict): o = o.get("model_file") or o.get("mesh") or next((v for v in o.values() if isinstance(v, str) and v.split("?")[0].endswith(".glb")), None)
        if isinstance(o, list): o = next((x for x in o if str(x).split("?")[0].endswith(".glb")), o[0] if o else None)
        if not o: raise PV.ProviderError("replicate 3d: no GLB in output")
        return o

ADAPTERS = dict(meshy=Meshy, tripo=Tripo, replicate=Replicate3D)
ENV = dict(meshy="MESHY_API_KEY", tripo="TRIPO_API_KEY", replicate="REPLICATE_API_TOKEN")

def standee_glb(image, out, aspect=None):
    """Offline DRAFT 'model': one double-sided textured card (glTF 2.0 binary, embedded JPEG/PNG). Valid GLB, not real 3D."""
    img = Path(image).read_bytes(); mime = "image/png" if img[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    w, h = aspect or (0.7, 1.0)
    pos = struct.pack("<12f", -w / 2, 0, 0, w / 2, 0, 0, w / 2, h, 0, -w / 2, h, 0)
    uv = struct.pack("<8f", 0, 1, 1, 1, 1, 0, 0, 0); idx = struct.pack("<6H", 0, 1, 2, 0, 2, 3)
    def pad(b, c=b"\x00"): return b + c * ((4 - len(b) % 4) % 4)
    chunks = [pad(pos), pad(uv), pad(idx), pad(img)]; offs = [0]
    for c in chunks[:-1]: offs.append(offs[-1] + len(c))
    binb = b"".join(chunks)
    g = dict(asset=dict(version="2.0", generator="seatcrew draft standee"), scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0)],
             meshes=[dict(primitives=[dict(attributes=dict(POSITION=0, TEXCOORD_0=1), indices=2, material=0)])],
             materials=[dict(pbrMetallicRoughness=dict(baseColorTexture=dict(index=0), metallicFactor=0, roughnessFactor=1), doubleSided=True)],
             textures=[dict(source=0)], images=[dict(bufferView=3, mimeType=mime)],
             accessors=[dict(bufferView=0, componentType=5126, count=4, type="VEC3", min=[-w / 2, 0, 0], max=[w / 2, h, 0]),
                        dict(bufferView=1, componentType=5126, count=4, type="VEC2"), dict(bufferView=2, componentType=5123, count=6, type="SCALAR")],
             bufferViews=[dict(buffer=0, byteOffset=offs[0], byteLength=48, target=34962), dict(buffer=0, byteOffset=offs[1], byteLength=32, target=34962),
                          dict(buffer=0, byteOffset=offs[2], byteLength=12, target=34963), dict(buffer=0, byteOffset=offs[3], byteLength=len(img))],
             buffers=[dict(byteLength=len(binb))])
    js = pad(json.dumps(g, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(js) + 8 + len(binb)
    Path(out).write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(binb), b"BIN\x00") + binb)
    return Path(out)

def make(image, out, pref="auto", allow_draft=True):
    order = [pref] if pref not in (None, "", "auto") else [b for b in ("meshy", "tripo", "replicate") if os.getenv(ENV[b])]
    errs = []
    for b in order:
        if b == "draft": break
        try: return ADAPTERS[b]().run(image, out), dict(backend=b)
        except (PV.ProviderError, KeyError) as e: errs.append(f"{b}: {e}")
    if allow_draft and pref in (None, "", "auto", "draft"): return standee_glb(image, out), dict(backend="draft", draft=True, errors=errs)
    raise PV.ProviderError("; ".join(errs) or "no 3D backend (set MESHY_API_KEY, TRIPO_API_KEY or REPLICATE_API_TOKEN)")
