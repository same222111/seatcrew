"""Example 4: AI short-video studio.

    topic -> TOPIC -> WRITER -> SCRIPTCHECK -> VOICE -> VISUALS -> EDITOR -> QC -> APPROVE (human)
                        ^           |  BLOCKED -> rewrite with the reason        |
                        +-----------+  QC failure -> back to the responsible seat (WRITER / VOICE / VISUALS / EDITOR)

* WRITER writes the script + storyboard (shots, durations, camera moves, captions) with its AI, or - with no AI - turns
  your notes / script lines into shots using the template.
* VOICE: ElevenLabs or OpenAI TTS (keys from .env), free edge-tts neural voices, or a labeled DRAFT robot voice offline.
* VISUALS: your own clips (clips folder, <shot id>.mp4/.png), Replicate video models (Kling/Luma/...), OpenAI or
  Stability images, or labeled DRAFT title cards offline.
* EDITOR: ffmpeg, 1080x1920 (or 1920x1080), camera motion, crossfades, karaoke subtitles, music ducking, -14 LUFS, H.264.
* QC: automated checks; failures go back to the responsible seat (bounded rounds), then the item blocks with the report.
* Anything made with a draft backend is marked "DRAFT PREVIEW - NOT FINAL QUALITY" in the UI, the video and its name.
Run:  seatcrew ui short_video      CLI assembly from your own clips:  seatcrew video assemble <folder>"""
import json, re, shutil
from pathlib import Path
from seatcrew import Seat, HumanSeat, Chief, Workflow, llm
from seatcrew.config import Config, base_defaults
from seatcrew.video import TEMPLATES, SIZES, validate_storyboard, key_status, tts as TTS, visuals as VIS, editor as ED, qc as QC, voices as VO, providers as PV
from seatcrew.video import characters as CH, imagegen as IG, lipsync as LS, storyboard as SB
from seatcrew.video.ff import have_ffmpeg, FFError

SEATS = ["chief", "topic", "writer", "scriptcheck", "voice", "visuals", "lipsync", "editor", "qc", "approve"]
PROMPTS = {
    "chief": "You are CHIEF of a short-video studio. Given today's video topics, answer proceed or hold.",
    "writer": "You are WRITER, a short-video scriptwriter. Write tight spoken narration (plain words, short sentences) and a shot-by-shot storyboard.",
    "scriptcheck": "You are SCRIPT CHECK. Is this script safe and honest (no medical/financial promises, hate, personal data, misleading claims)? Answer ok or unsafe.",
}
SETTINGS = {"template": "knowledge_explainer", "aspect": "9:16", "tts_backend": "auto", "tts_voice": "", "visuals_backend": "auto",
            "video_model": "", "image_model": "", "clips_dir": "", "bgm_path": "", "bgm_gain_db": -18.0, "allow_draft": True,
            "max_rewrites": 2, "banned_phrases": ["guaranteed", "risk-free", "miracle", "100% safe", "cure", "get rich"],
            "min_sharpness": 12.0, "crf": 18, "preset": "slow", "approve_auto_approve": False, "load_samples": False, "speaker_colors": True,
            "max_video_usd": 20.0, "cast": "", "image_backend": "auto", "keyframes": False, "lipsync_backend": "none", "continuity_qc": True}
CHOICES = {"template": list(TEMPLATES), "aspect": list(SIZES), "tts_backend": ["auto", "elevenlabs", "minimax", "doubao", "azure", "openai", "edge", "draft"],
           "visuals_backend": ["auto", "kling", "runway", "gemini", "minimax", "luma", "replicate", "openai", "stability", "draft"], "preset": ["slow", "medium", "fast", "veryfast", "ultrafast"],
           "image_backend": ["auto", *IG.ADAPTERS, "draft"], "lipsync_backend": ["none", *LS.ADAPTERS]}
SAMPLES = [dict(topic="Why is the sky blue?", template="knowledge_explainer",
                notes="Sunlight looks white, but it is a mix of every color. Air molecules scatter short blue waves much more than long red ones. "
                      "So blue light reaches your eyes from every part of the sky. At sunset, light travels through more air and the blue is scattered away. That is why sunsets glow orange and red.")]

def estimate_sec(text, wpm):
    n = len(TTS.tokens(text)); cjk = bool(TTS.CJK.search(text))
    return (n / (4.5 if cjk else wpm / 60.0)) + 0.5

def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+|\n+", text or "") if s.strip()]

class Topic(Seat):
    name = "topic"; job = "checks the brief"
    def rules(self, it):
        d = it["data"]; s = self.cfg["settings"]
        d["topic"] = (d.get("topic") or "").strip()
        if not d["topic"]: return False, "no topic"
        user_aspect = d.get("aspect"); d["template"] = d.get("template") or s["template"]; d["aspect"] = d.get("aspect") or s["aspect"]
        if d["template"] not in TEMPLATES: return False, f"unknown template {d['template']}"
        if d["aspect"] not in SIZES: return False, f"aspect must be one of {list(SIZES)}"
        d["cast"] = d.get("cast") or s.get("cast") or ""
        if d["cast"]:
            try: cast = CH.Store().cast(d["cast"])
            except ValueError as e: return False, str(e)
            d["cast_members"] = [m["character"] for m in cast["members"]]
            if not d.get("notes") and cast.get("plot"): d["notes"] = cast["plot"]
        elif TEMPLATES[d["template"]].get("needs_cast"): return False, f"{d['template']} needs a cast - pick one in Character Studio (Shoot with this cast)"
        if d["template"] in TEMPLATES and TEMPLATES[d["template"]].get("aspect") and not user_aspect: d["aspect"] = TEMPLATES[d["template"]]["aspect"]
        return True, f"{TEMPLATES[d['template']]['label']} · {d['aspect']} · {d['topic'][:60]}"

class Writer(Seat):
    name = "writer"; job = "script + storyboard"; kind = "producer"
    def rules(self, it):
        d = it["data"]; tp = TEMPLATES[d["template"]]; fb = d.get("feedback", {}).get("writer")
        out = self.ai_write(d, tp, fb)
        if out: sb, who = out
        else: sb, who = self.from_notes(d, tp, fb), "template"
        d["storyboard"] = sb; d.pop("feedback", None) if fb else None
        return True, f"{len(sb['shots'])} shots, ~{sum(s['duration'] for s in sb['shots']):.0f}s ({who})"
    def ai_write(self, d, tp, fb):
        if d.get("cast"):
            st = CH.Store(); cast = st.cast(d["cast"]); names = d["cast_members"]
            castp = (f"CAST (only these characters may speak or appear; use their exact names):\n{CH.cast_brief(st, cast)}\n"
                     + (f"Coverage: {' / '.join(tp['coverage'])}. " if tp.get("coverage") else "") +
                     'Every shot needs "lines": [{"speaker": "<cast name>", "text": "...", "emotion": "..."}], "characters": [names visible in the shot], '
                     '"shot_type": "wide|two_shot|ots|closeup|reaction|insert". No narrator.\n')
        else: castp = ""
        prompt = castp + (f"Topic: {d['topic']}\nNotes: {d.get('notes', '')}\nTemplate: {tp['label']} - arc: {' / '.join(tp['arc'])}\n"
                  f"Language: {self.cfg['language']}. Speaking pace {tp['wpm']} words/min. {tp['shots'][0]}-{tp['shots'][1]} shots, each {tp['shot_sec'][0]}-{tp['shot_sec'][1]}s, "
                  f"total {tp['total_sec'][0]}-{tp['total_sec'][1]}s. Max {tp['max_words_per_sentence']} words per sentence. Visual style: {tp['visual_style']}.\n"
                  + (f"Characters with saved voices: {', '.join(n for n in VO.Library().all() if n != 'narrator')}. For dialogue use \"lines\": "
                     f"[{{\"speaker\": \"narrator|<character>\", \"text\": \"...\", \"emotion\": \"{'|'.join(VO.STYLES)}\"}}] instead of narration.\n"
                     if VO.Library().all() else "")
                  + (f"REWRITE - the previous version was rejected: {fb}\n" if fb else "") +
                  'Reply ONLY with JSON: {"title": "...", "shots": [{"id": "s01", "narration": "...", "duration": 4.0, "caption": "short on-screen text or empty", '
                  '"visual": "detailed image/video prompt, no text in image", "camera": "push_in|pull_out|pan_left|pan_right|pan_up|pan_down|static", "transition": "crossfade|fade_black|cut"}]}')
        r = llm.write(self.name, prompt, self.cfg, max_tokens=2500)
        if not r: return None
        m = re.search(r"\{.*\}", r[0], re.S)
        try: sb = validate_storyboard(dict(json.loads(m.group(0)), aspect=d["aspect"], language=self.cfg["language"], template=d["template"]))
        except (AttributeError, ValueError) as e: self.wf.log(self.name, "AI-ERR", f"storyboard rejected: {e}", it_subject(d)); return None
        return sb, r[1]
    def from_cast(self, d, tp):
        """No AI + a cast: "Name: line" rows in your notes become dialogue; unlabeled sentences go to the cast in turn.
        Shot/reverse-shot coverage from the template; nobody outside the cast speaks."""
        names = d["cast_members"]; rows = []
        for ln in [x.strip() for x in re.split(r"\n+", d.get("notes") or "") if x.strip()]:
            m = re.match(r"^([^:：]{1,40})[:：]\s*(.+)$", ln)
            if m and m.group(1).strip() in names: rows.append((m.group(1).strip(), m.group(2).strip()))
            else:
                for t in sentences(ln): rows.append((names[len(rows) % len(names)], t))
        if not rows: rows = [(names[0], d["topic"])]
        cams = tp["cameras"]; shots = []; prev = None
        for i, (sp, t) in enumerate(rows):
            first, last = i == 0, i == len(rows) - 1
            st = "wide" if (first or last) and len(names) > 1 else ("ots" if prev and prev != sp and i % 2 else "closeup")
            who = names if st == "wide" else ([sp, prev] if st == "ots" and prev else [sp])
            shots.append(dict(id=f"s{i + 1:02d}", lines=[dict(speaker=sp, text=t)], duration=round(min(max(estimate_sec(t, tp["wpm"]) + .4, tp["shot_sec"][0]), tp["shot_sec"][1] + 2), 1),
                              caption="", visual=f"{st.replace('_', ' ')} shot: {sp} says \"{t}\" - {', '.join(who)} in frame. {tp['visual_style']}",
                              camera=cams[i % len(cams)], transition=tp["transition"], characters=who, shot_type=st))
            prev = sp
        return validate_storyboard(dict(title=d["topic"], aspect=d["aspect"], language=self.cfg["language"], template=d["template"], shots=shots))
    def from_notes(self, d, tp, fb):
        if d.get("cast"): return self.from_cast(d, tp)
        """No AI: each sentence of your notes/script becomes narration; long sentences are split; the template sets camera,
        captions and pacing. Honest: it never invents facts."""
        lim = tp["max_words_per_sentence"]; maxw = int(tp["shot_sec"][1] * tp["wpm"] / 60) - 1; out = []
        for s in sentences(d.get("notes") or d["topic"]):
            ws = s.split()
            while len(ws) > lim:                                   # split long sentences at a comma near the middle, else in half
                cut = next((i + 1 for i in range(len(ws) // 2, len(ws) - 2) if ws[i].endswith(",")), None) or next((i + 1 for i in range(len(ws) // 2, 1, -1) if ws[i].endswith(",")), None) or len(ws) // 2
                out.append(" ".join(ws[:cut])); ws = ws[cut:]
            out.append(" ".join(ws))
        shots, cur = [], ""
        for s in out:                                              # merge very short lines into one shot
            if cur and len((cur + " " + s).split()) <= maxw and len(cur.split()) < 6: cur += " " + s
            else:
                if cur: shots.append(cur)
                cur = s
        if cur: shots.append(cur)
        cams = tp["cameras"]; sb = dict(title=d["topic"], aspect=d["aspect"], language=self.cfg["language"], template=d["template"], shots=[])
        for i, n in enumerate(shots):
            sb["shots"].append(dict(id=f"s{i + 1:02d}", narration=n, duration=round(min(max(estimate_sec(n, tp["wpm"]), tp["shot_sec"][0]), tp["shot_sec"][1] + 2), 1),
                                    caption=(d["topic"].upper()[:40] if i == 0 else ""), visual=f"{n} - {tp['visual_style']}", camera=cams[i % len(cams)],
                                    transition=tp["transition"] if i < len(shots) - 1 else "crossfade"))
        return validate_storyboard(sb)

def it_subject(d): return d.get("topic", "-")[:30]

class ScriptCheck(Seat):
    name = "scriptcheck"; job = "readability, safety, timing"; labels = ("ok", "unsafe"); block_labels = ("unsafe",)
    def rules(self, it):
        d = it["data"]; sb = d.get("storyboard"); tp = TEMPLATES[d["template"]]; s = self.cfg["settings"]
        if not sb: return False, "no storyboard"
        text = " ".join(x["narration"] for x in sb["shots"]); probs = []
        hit = [p for p in s["banned_phrases"] if p.lower() in text.lower()]
        if hit: probs.append("unsafe phrase: " + ", ".join(hit))
        if d.get("cast"):
            names = set(d["cast_members"])
            outside = sorted({l["speaker"] for x in sb["shots"] for l in x.get("lines") or [] if l["speaker"] not in names} | {c for x in sb["shots"] for c in x.get("characters") or [] if c not in names})
            if outside: probs.append("not in the cast: " + ", ".join(outside))
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{3}[- ]?\d{3}[- ]?\d{4}\b", text): probs.append("contains an email address or phone number")
        empty = [x["id"] for x in sb["shots"] if not x["narration"]]
        if empty: probs.append("shots without narration: " + ", ".join(empty))
        long_ = [f"{x['id']} ({len(t.split())} words)" for x in sb["shots"] for t in sentences(x["narration"]) if not TTS.CJK.search(t) and len(t.split()) > tp["max_words_per_sentence"]]
        if long_: probs.append(f"sentences over {tp['max_words_per_sentence']} words: " + ", ".join(long_))
        slow = [f"{x['id']} needs ~{estimate_sec(x['narration'], tp['wpm']):.1f}s > {tp['shot_sec'][1] + 2:.0f}s" for x in sb["shots"] if estimate_sec(x["narration"], tp["wpm"]) > tp["shot_sec"][1] + 2]
        if slow: probs.append("shot too long to read: " + ", ".join(slow))
        tot = sum(max(x["duration"], estimate_sec(x["narration"], tp["wpm"])) for x in sb["shots"]); lo, hi = tp["total_sec"]
        if not lo * 0.5 <= tot <= hi: probs.append(f"total ~{tot:.0f}s outside {lo * 0.5:.0f}-{hi}s")
        if probs: it["_back"] = "writer"; d.setdefault("feedback", {})["writer"] = "; ".join(probs); return False, "; ".join(probs)
        return True, f"readable, safe words, ~{tot:.0f}s"
    def ai_prompt(self, it): return "\n".join(x["narration"] for x in it["data"]["storyboard"]["shots"])

class Voice(Seat):
    name = "voice"; job = "narration (TTS)"; kind = "producer"
    def rules(self, it):
        d = it["data"]; s = self.cfg["settings"]; work = self.wf.item_dir(it) / "voice"; work.mkdir(parents=True, exist_ok=True)
        info = []
        lib = VO.Library(); lang = self.cfg["language"]
        for sh in d["storyboard"]["shots"]:
            lines = sh.get("lines") or ([dict(speaker="narrator", text=sh["narration"])] if sh.get("narration") else [])
            if not lines: continue
            cast = any(l["speaker"] != "narrator" for l in lines) or "narrator" in lib.all() or not s["tts_voice"]
            try:
                if cast:                              # character voice library: one persistent voice per character
                    p, words, inf = VO.render_lines(lines, work / f"{sh['id']}.wav", lib, lang=lang, pref=None if s["tts_backend"] == "auto" else s["tts_backend"], allow_draft=s["allow_draft"])
                    sh["voices"] = inf; i = dict(backend=inf[0]["backend"], sync="exact" if all(x["sync"] == "exact" for x in inf) else "estimated",
                                                  draft=any(x["draft"] for x in inf), voice=inf[0]["voice"])
                else: p, words, i = TTS.synth(sh["narration"], work / sh["id"], pref=s["tts_backend"], voice=s["tts_voice"] or None, lang=lang, allow_draft=s["allow_draft"])
            except (TTS.TTSError, FFError, ValueError) as e: return False, f"{sh['id']}: {e}"
            sh["audio"], sh["words"] = str(p), words; info.append(i)
        if not info: return False, "no narration"
        d["voice"] = dict(backend=sorted({i["backend"] for i in info}), sync="estimated" if any(i["sync"] != "exact" for i in info) else "exact",
                          draft=any(i.get("draft") for i in info), voice=info[0].get("voice"), fallback=info[0].get("fallback_reasons"))
        return True, f"{'/'.join(d['voice']['backend'])} voice, {d['voice']['sync']} word timing" + (" · DRAFT" if d["voice"]["draft"] else "")

class Visuals(Seat):
    name = "visuals"; job = "per-shot images / clips"; kind = "producer"
    def rules(self, it):
        d = it["data"]; s = self.cfg["settings"]; work = self.wf.item_dir(it) / "visuals"; work.mkdir(parents=True, exist_ok=True)
        redo = set(d.pop("redo_shots", []) or []); tp = TEMPLATES[d["template"]]; clips = d.get("clips_dir") or s["clips_dir"] or None
        todo = [x for x in d["storyboard"]["shots"] if not (x.get("clip_path") and Path(x["clip_path"]).exists()) or x["id"] in redo]
        paid = [b for b in VIS.auto_order(s["visuals_backend"], s["video_model"]) if b in VIS.DIRECT]
        if todo and paid:                                   # cost/time estimate shown BEFORE any paid generation
            est = PV.estimate(todo, paid[0]); d["visuals_estimate"] = est
            if est["usd"] is not None and est["usd"] > float(s.get("max_video_usd") or 0):
                return False, f"{paid[0]} would cost ~${est['usd']} for {est['seconds']}s ({est['note']}) - over max_video_usd; approve or raise max_video_usd"
        refs = {n: p["ref_image"] for n, p in VO.Library().all().items() if p.get("ref_image")}
        set_sheet = None
        if d.get("cast"):                                   # locked character refs win for cast members
            st = CH.Store(); cast = st.cast(d["cast"]); refs.update({n: r[0] for n, r in st.cast_refs(cast).items()}); set_sheet = cast.get("set_sheet") or None
            allrefs = st.cast_refs(cast)
        for sh in d["storyboard"]["shots"]:
            if sh.get("clip_path") and sh["id"] not in redo and Path(sh["clip_path"]).exists(): continue
            if sh["id"] in redo and sh.get("visual_info", {}).get("backend") == "local":
                return False, f"{sh['id']}: your clip {sh['visual_info']['source']} failed QC - replace it in the clips folder"
            if d.get("cast") and s.get("keyframes"):       # keyframe: one image with the set sheet + every character in the shot, then image-to-video
                kr = ([set_sheet] if set_sheet else []) + [allrefs[c][0] for c in sh.get("characters") or [] if c in allrefs]
                try:
                    kp, ki = IG.generate(VIS.prompt_for(sh, tp["visual_style"]), work / f"{sh['id']}_key.png", kr, d["aspect"], s["image_backend"], s["image_model"] or None, s["allow_draft"])
                    if not ki.get("draft"): sh["ref_image"] = str(kp)
                except (PV.ProviderError, FFError) as e: self.wf.log(self.name, "KEYFRAME", f"{sh['id']}: {e}", it_subject(d))
            try: p, info = VIS.make(sh, work, d["aspect"], pref=s["visuals_backend"], clips_dir=clips, video_model=s["video_model"], image_model=s["image_model"], style=tp["visual_style"], allow_draft=s["allow_draft"], refs=refs)
            except (VIS.VisualError, PV.ProviderError, FFError) as e: return False, f"{sh['id']}: {e}"
            sh["clip_path"], sh["visual_info"] = str(p), info
        bk = [x["visual_info"]["backend"] for x in d["storyboard"]["shots"]]
        d["visuals"] = dict(backends=sorted(set(bk)), draft="draft" in bk)
        return True, " · ".join(f"{b}×{bk.count(b)}" for b in sorted(set(bk))) + (" · DRAFT" if "draft" in bk else "")

class LipSync(Seat):
    name = "lipsync"; job = "lip-sync talking shots"; kind = "producer"
    def rules(self, it):
        d = it["data"]; s = self.cfg["settings"]; b = s.get("lipsync_backend") or "none"
        if b == "none": return True, "off (shots keep their original mouths)"
        work = self.wf.item_dir(it) / "lipsync"; work.mkdir(parents=True, exist_ok=True); done, kept = [], []
        for sh in d["storyboard"]["shots"]:
            if not sh.get("audio") or not sh.get("clip_path") or SB.is_image(sh["clip_path"]) or sh.get("shot_type") == "wide": continue
            if sh.get("lipsync") == sh["clip_path"]: continue
            p, info = LS.apply(sh["clip_path"], sh["audio"], work / f"{sh['id']}.mp4", b)
            if info.get("lipsync") == b: sh["clip_path"] = sh["lipsync"] = str(p); done.append(sh["id"])
            else: kept.append(f"{sh['id']} ({(info.get('error') or info.get('note') or 'skipped')[:60]})")
        return True, f"{b}: synced {len(done)} shot(s)" + (f"; kept original: {', '.join(kept)}" if kept else "")

class Editor(Seat):
    name = "editor"; job = "ffmpeg edit + mix"; kind = "producer"
    def rules(self, it):
        if not have_ffmpeg(): return False, "ffmpeg not found - install ffmpeg and retry"
        d = it["data"]; s = self.cfg["settings"]; sb = d["storyboard"]; tp = TEMPLATES[d["template"]]; od = self.wf.item_dir(it)
        draft = bool(d.get("voice", {}).get("draft") or d.get("visuals", {}).get("draft"))
        shots = [dict(id=x["id"], clip=x["clip_path"], camera=x["camera"], transition=x["transition"], caption=x["caption"], duration=x["duration"], audio=x.get("audio"), words=x.get("words", []), voices=x.get("voices", [])) for x in sb["shots"]]
        cols = {n: p["color"] for n, p in VO.Library().all().items() if p.get("color") and n != "narrator"} if s["speaker_colors"] else None
        bgm = s["bgm_path"] if s["bgm_path"] and Path(s["bgm_path"]).is_file() and not tp.get("no_music") else None
        room = dict(room_tone_db=tp["room_tone_db"], reverb=tp.get("reverb", 0)) if tp.get("room_tone_db") is not None else {}
        for f in od.glob("final*.mp4"): f.unlink()
        try:
            man = ED.assemble(shots, od / "final.mp4", od / "work", aspect=d["aspect"], size=self.wf.size_override, bgm=bgm, draft=draft,
                              transition_sec=tp["transition_sec"], speaker_colors=cols, bgm_gain_db=s["bgm_gain_db"] if s["bgm_gain_db"] != -18.0 else tp["bgm_gain_db"],
                              **dict(dict(crf=s["crf"], preset=s["preset"], **room), **self.wf.editor_opts))
        except (FFError, ValueError) as e: return False, str(e)[-400:]
        d["video"] = dict(file=Path(man["output"]).name, total=man["total"], size=man["size"], draft=draft)
        d["timeline"] = [dict(id=x["id"], start=x["start"], dur=x["dur"], kind=x.get("kind"), src=f"{x.get('src_w')}x{x.get('src_h')}") for x in man["shots"]]
        (od / "storyboard.json").write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, f"{man['size'][0]}x{man['size'][1]} {man['total']:.1f}s -> {d['video']['file']}"

class QualityCheck(Seat):
    name = "qc"; job = "automated quality check"
    def rules(self, it):
        d = it["data"]; od = self.wf.item_dir(it); tp = TEMPLATES[d["template"]]
        man = json.loads((od / "work" / "manifest.json").read_text(encoding="utf-8"))
        if d.get("cast") and self.cfg["settings"].get("continuity_qc", True):
            st = CH.Store(); cast = st.cast(d["cast"]); by = {x["id"]: x for x in d["storyboard"]["shots"]}
            man["continuity"] = dict(refs=st.cast_refs(cast), set_sheet=cast.get("set_sheet") or None,
                                     shots=[dict(id=x["id"], start=x["start"], dur=x["dur"], camera=x.get("camera"), characters=by.get(x["id"], {}).get("characters") or []) for x in man["shots"]],
                                     thresholds=self.wf.qc_opts.get("continuity_thresholds"))
        r = QC.check(man, dict(total_sec=self.wf.qc_total or (tp["total_sec"][0] * 0.5, tp["total_sec"][1] * 1.2), sync=d.get("voice", {}).get("sync")),
                     **dict(dict(min_sharpness=self.cfg["settings"]["min_sharpness"]), **{k: v for k, v in self.wf.qc_opts.items() if k != "continuity_thresholds"}))
        d["qc"] = r; (od / "quality_report.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if not r["passed"]:
            it["_back"] = r["send_back"]; fails = [c for c in r["checks"] if not c["ok"] and c["severity"] == "fail" and c["seat"] == r["send_back"]]
            if r["send_back"] == "visuals":
                bad = {x["id"] for x in man["shots"] if any(x["id"] in c["detail"] for c in fails)}
                d["redo_shots"] = sorted(bad) or [x["id"] for x in man["shots"]]
            if r["send_back"] == "writer": d.setdefault("feedback", {})["writer"] = "; ".join(c["detail"] for c in fails)
            return False, r["summary"]
        return True, r["summary"] + f" · {sum(c['ok'] for c in r['checks'])}/{len(r['checks'])} checks"

class Approve(HumanSeat):
    name = "approve"; job = "human sign-off"

class ShortVideo(Workflow):
    name = "short_video"; title = "AI short-video studio"; studio = "video"
    locale_dirs = (Path(__file__).parent / "locales",)
    submit_fields = [dict(name="topic", label="Topic"), dict(name="notes", label="Notes or your script (one sentence per line = one shot)", type="textarea"),
                     dict(name="template", label="Template", type="select", options=list(TEMPLATES)), dict(name="aspect", label="Aspect", type="select", options=list(SIZES)),
                     dict(name="clips_dir", label="Clips folder (optional)"), dict(name="cast", label="Cast (Character Studio, optional)")]
    size_override = None; editor_opts = {}; qc_opts = {}; qc_total = None          # tests use tiny frames
    def __init__(self, cfg, state_dir):
        super().__init__(cfg, state_dir)
        self.setup([Chief(self), Topic(self), Writer(self), ScriptCheck(self), Voice(self), Visuals(self), LipSync(self), Editor(self), QualityCheck(self), Approve(self)])
        if not self.items and cfg["settings"]["load_samples"]:
            for s in SAMPLES: self.inbox.append(self.new_item(s["topic"], s, "video"))
    def submit(self, title=None, data=None, subject="video"):
        data = {k: v for k, v in dict(data or {}).items() if v not in (None, "")}
        return super().submit(title or data.get("topic", "video"), data, subject)
    def item_dir(self, it):
        p = self.state_dir / "videos" / str(it["id"]); p.mkdir(parents=True, exist_ok=True); return p
    def media_file(self, item_id, name):
        """Files the dashboard may fetch: the video, its report and storyboard. Nothing outside the item folder."""
        if not re.fullmatch(r"\d{1,9}", str(item_id)) or not re.fullmatch(r"(final(_DRAFT)?\.mp4|quality_report\.json|storyboard\.json)", name): return None
        p = self.state_dir / "videos" / str(item_id) / name; return p if p.is_file() else None
    def run_chain(self, item, start=0):
        """Seats may send an item back (SCRIPT CHECK -> WRITER, QC -> the responsible seat). Bounded by max_rewrites per seat."""
        while True:
            r = super().run_chain(item, start); back = item.pop("_back", None)
            if r is not False or not back or back not in [s.name for s in self.chain]: return r
            rounds = item["data"].setdefault("rounds", {}); n = rounds.get(back, 0)
            if n >= int(self.cfg.data["settings"]["max_rewrites"]):
                self.log(back, "HOLD", f"#{item['id']} still failing after {n} round(s) - needs you", self.subject(item)); return r
            rounds[back] = n + 1; start = [s.name for s in self.chain].index(back)
            self.log(back, "REWRITE", f"#{item['id']} sent back to {back.upper()} (round {n + 1}): {item['chain'][-1]['reason'][:160]}", self.subject(item))
            item["status"] = f"rework at {back.upper()}"
    def item_view(self, it):
        v = super().item_view(it); d = dict(v.get("data", {}))
        if d.get("storyboard"):
            d["storyboard"] = dict(d["storyboard"], shots=[{k: x for k, x in s.items() if k not in ("words", "audio", "clip_path")} for s in d["storyboard"]["shots"]])
        d.pop("feedback", None); v["data"] = d; return v
    def definition(self):
        return dict(super().definition(), studio="video", choices=CHOICES, keys=key_status())

def validate(c):
    s = c["settings"]
    for k, opts in CHOICES.items():
        if s.get(k) not in opts: raise ValueError(f"settings.{k} must be one of {opts}")
    if not 0 <= int(s["crf"]) <= 28: raise ValueError("settings.crf must be 0-28 (18 = high quality)")
    if not 0 <= int(s["max_rewrites"]) <= 5: raise ValueError("settings.max_rewrites must be 0-5")
    if not -40 <= float(s["bgm_gain_db"]) <= 0: raise ValueError("settings.bgm_gain_db must be -40..0")

def build(config_path, state_dir):
    return ShortVideo(Config(config_path, base_defaults(SEATS, PROMPTS, SETTINGS), validate), state_dir)
