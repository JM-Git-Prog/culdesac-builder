#!/usr/bin/env python3
"""
neighbourhood-service.py - "type a sentence, get a neighbourhood" - on http://127.0.0.1:8196/

  sentence  -> brief writer (nuextract on local Ollama; a word-rules fallback if Ollama is down)
            -> brief.json in jobs/<stamp>/
            -> UPBGE 0.50 headless (blender.exe --background --python run-brief.py -- <job>)
            -> pictures + neighbourhood.blend in that job folder, shown on the page as they arrive.

Standard library only. Binds 127.0.0.1 only. One build at a time. Never deletes anything.
Start with START-NEIGHBOURHOOD-BUILDER.bat.
"""
import base64, hashlib, json, os, re, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.join(HERE, "jobs")
PORT = 8196
OLLAMA = "http://127.0.0.1:11434"
MODEL = "nuextract:latest"          # lane winner 2026-09-02: local, 2 GB, valid JSON on the first try
BLENDER_CANDIDATES = [r"C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe",
                      os.path.join(HERE, "..", "..", "01 Engines", "UPBGE 0.50", "blender.exe")]
BLENDER = next((p for p in BLENDER_CANDIDATES if os.path.exists(p)), None)
STYLES = ["colonial", "ranch", "modern", "cottage", "farmhouse", "georgian"]
WALLS = ["brick", "plaster", "concrete", "siding", "stone"]
COLORS = ["white", "beige", "grey", "blue", "red", "yellow", "green", "natural"]
ROOFS = ["clay", "ceramic", "metal", "flat", "shingle"]
SCHEMA = {"type": "object", "properties": {
    "name": {"type": "string"}, "layout": {"type": "string", "enum": ["cul-de-sac", "straight"]},
    "house_count": {"type": "integer", "minimum": 1, "maximum": 8},
    "houses": {"type": "array", "items": {"type": "object", "properties": {
        "style": {"type": "string", "enum": STYLES}, "stories": {"type": "integer", "enum": [1, 2, 3]},
        "wall": {"type": "string", "enum": WALLS}, "wall_color": {"type": "string", "enum": COLORS},
        "roof": {"type": "string", "enum": ROOFS}, "garage": {"type": "string", "enum": ["left", "right", "none"]},
        "porch": {"type": "boolean"}, "features": {"type": "array", "items": {"type": "string"}}},
        "required": ["style", "stories", "wall", "wall_color", "roof", "garage", "porch", "features"]}},
    "trees": {"type": "string", "enum": ["few", "some", "many"]},
    "sky": {"type": "string", "enum": ["clear", "cloudy", "sunset", "overcast"]},
    "other_features": {"type": "array", "items": {"type": "string"}}},
    "required": ["name", "layout", "house_count", "houses", "trees", "sky", "other_features"]}
SYSTEM = ("You turn a homeowner's sentence into a neighbourhood order form (JSON). Always fill every field. "
          "If the sentence says multiple, several or a few homes, use 4-6 houses; 'a couple' means 2; a number means that number. "
          "Make the houses DIFFERENT from each other in style, wall, colour and roof unless the sentence says they match. "
          "Styles: colonial (2 stories, brick, gable roof), ranch (1 story, plaster, hip roof, wide), modern (2 stories, "
          "concrete, flat roof), cottage (1 story, siding or plaster, porch, metal or shingle roof), farmhouse (2 stories, "
          "white siding, porch), georgian (3 stories, red brick, HIPPED roof, white trim, MUCH LARGER than the others — "
          "the grand, stately, symmetrical, presidential, mansion, manor or estate house; use this whenever the sentence "
          "asks for something bigger, grander or statelier than its neighbours). "
          "Default sky clear, trees some, layout cul-de-sac. Give the place a short pleasant street name.")

_lock = threading.Lock()
_current = {"job": None}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ models (the house law: the 4090 is scarce, the Pro plan is prepaid)
# Lane winners, cheapest rung that passed first (2026-09-03, tested through the connector):
#   gpt-oss:120b-cloud   - exact form + correct edits with the key template, 1.9 s, 4090 untouched
#   deepseek-v4-flash:cloud - good content, drifts on key names (tolerant mapping below)
#   nuextract:latest     - local, needs the JSON schema; occupies the 4090 for a moment
# Cloud tags ignore Ollama's `format` schema, so the template goes into the prompt for them.
PREFER = ["gpt-oss:120b-cloud", "deepseek-v4-flash:cloud", "qwen3.5:397b-cloud", "nuextract:latest", "llama3.1:latest"]
TEMPLATE = ('Reply with ONLY a JSON object with EXACTLY these keys and allowed values - no other keys, no comments:\n'
            '{"name": "<short street name>", "layout": "cul-de-sac"|"straight", "house_count": 1-8, "houses": [{"style": "colonial"|"ranch"|"modern"|"cottage"|"farmhouse"|"georgian", '
            '"stories": 1|2|3, "wall": "brick"|"plaster"|"concrete"|"siding"|"stone", "wall_color": "white"|"beige"|"grey"|"blue"|"red"|"yellow"|"green"|"natural", '
            '"roof": "clay"|"ceramic"|"metal"|"flat"|"shingle", "garage": "left"|"right"|"none", "porch": true|false, '
            '"features": ["<house-level asks the fields above cannot hold - columns, a portico, a pediment, dormers, chimneys, ...>"]}, ...], '
            '"trees": "few"|"some"|"many", "sky": "clear"|"cloudy"|"sunset"|"overcast", '
            '"other_features": ["<anything else asked that the fields above cannot hold - a fountain, a gate, "presidential", ...>"]}\n'
            'NOTHING the homeowner asks may be dropped: what the fixed fields cannot hold goes, in the homeowner\'s own words, into that house\'s "features" '
            'or into "other_features" (the street and grounds); both are [] only when everything fits the fields.')
REVISE_SYSTEM = ("You edit a neighbourhood order form (JSON) from a homeowner's instruction. " + TEMPLATE +
                 "\nKeep everything from the current form that the instruction does not mention. Houses are numbered from 1 in array order (\"house 2\" = houses[1]). "
                 "'Add a home' appends a house different from the others; 'remove house N' deletes it. "
                 "Whatever the instruction asks that no field can hold is added to that house's \"features\" or to \"other_features\" - never dropped.")
_garage = {"tags": [], "at": 0.0}


def garage():
    """Census, cached 60 s: which tags the local daemon can run right now (cloud tags included)."""
    if time.time() - _garage["at"] < 60 and _garage["tags"]:
        return _garage["tags"]
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
            _garage["tags"] = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        log("garage census failed: %s" % e); _garage["tags"] = []
    _garage["at"] = time.time()
    return _garage["tags"]


def pick_models(text):
    """Ordered lane for this sentence: an explicit 'use <tag>' first, then the house-law preference, cloud before local."""
    tags = garage()
    lane = []
    m = re.search(r"\buse\s+([\w.:/-]+)", text, re.I)
    if m:
        want = m.group(1).rstrip(":,.")
        hit = next((t for t in tags if t == want or t.split(":")[0] == want.split(":")[0]), None)
        if hit: lane.append(hit)
        else: log("'use %s' - not in the garage, falling through" % want)
    lane += [t for t in PREFER if t in tags and t not in lane]
    return lane


def is_cloud(tag):
    return tag.endswith(":cloud") or tag.endswith("-cloud")


def ask(tag, system, user):
    body = {"model": tag, "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if not is_cloud(tag):
        body["format"] = SCHEMA                       # local models honour the schema; cloud tags ignore it
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        reply = json.loads(r.read())
    content = reply["message"]["content"].strip()
    if content.startswith("```"):
        content = content.strip("`"); content = content[content.find("{"):]
    return json.loads(content[content.find("{"):content.rfind("}") + 1])


def tolerant(b):
    """Map the key drift cloud models show (streetName, colour, garage: true, roof gable/hip) onto the form."""
    if not isinstance(b, dict): return {}
    out = dict(b)
    out["name"] = b.get("name") or b.get("street_name") or b.get("streetName") or "New Neighbourhood"
    if "other_features" not in b: out["other_features"] = b.get("otherFeatures") or b.get("extras") or b.get("features") or []
    houses = []
    for i, h in enumerate(b.get("houses") or []):
        if not isinstance(h, dict): continue
        h = dict(h)
        if "features" not in h: h["features"] = h.get("extras") or h.get("other_features") or []
        if "wall_color" not in h: h["wall_color"] = h.get("colour") or h.get("color") or "natural"
        if h.get("wall_color") == "gray": h["wall_color"] = "grey"
        if h.get("roof") in ("gable", "hip", "pitched"): h["roof"] = {"colonial": "clay", "ranch": "ceramic"}.get(h.get("style"), "shingle")
        g = h.get("garage")
        if g is True: h["garage"] = "right" if i % 2 == 0 else "left"
        elif g is False or g is None: h["garage"] = "none"
        houses.append(h)
    out["houses"] = houses
    if not isinstance(out.get("house_count"), int): out["house_count"] = len(houses)
    return out


def ollama_brief(text, current=None):
    """Fresh brief (current=None) or a revision of `current` per the instruction. Walks the lane; reports which tag answered."""
    errors = []
    for tag in pick_models(text):
        try:
            if current is None:
                raw = ask(tag, SYSTEM + " " + TEMPLATE, text)
            else:
                raw = ask(tag, REVISE_SYSTEM, "CURRENT FORM:\n%s\n\nINSTRUCTION: %s" % (json.dumps(current), text))
            return tolerant(raw), tag
        except Exception as e:
            errors.append("%s: %s" % (tag, str(e)[:120])); log("brief lane %s failed: %s" % (tag, str(e)[:200]))
    raise RuntimeError("; ".join(errors) or "no model in the garage")


def rules_brief(text):
    """No model? Word rules. Honest but dull."""
    t = text.lower()
    m = re.search(r"\b(\d+)\b", t)
    n = int(m.group(1)) if m else (5 if any(w in t for w in ("multiple", "several", "bunch", "many")) else (2 if "couple" in t else 4))
    n = max(1, min(8, n))
    layout = "straight" if any(w in t for w in ("straight", "street", "avenue", "road")) and "cul" not in t else "cul-de-sac"
    sky = "sunset" if any(w in t for w in ("sunset", "evening", "dusk")) else ("overcast" if "overcast" in t else ("cloudy" if "cloud" in t else "clear"))
    trees = "many" if any(w in t for w in ("forest", "wooded", "lots of trees", "many trees")) else ("few" if "few trees" in t or "no trees" in t else "some")
    houses = []
    for i in range(n):
        st = STYLES[i % len(STYLES)]
        houses.append({"style": st, "stories": 2 if st in ("colonial", "modern", "farmhouse") else 1,
                       "wall": {"colonial": "brick", "ranch": "plaster", "modern": "concrete", "cottage": "plaster", "farmhouse": "siding"}[st],
                       "wall_color": ["natural", "beige", "grey", "blue", "white", "yellow"][i % 6],
                       "roof": {"colonial": "clay", "ranch": "ceramic", "modern": "flat", "cottage": "metal", "farmhouse": "metal"}[st],
                       "garage": ["right", "left", "none"][i % 3], "porch": st in ("cottage", "farmhouse")})
    return {"name": "Word Rules Court", "layout": layout, "house_count": n, "houses": houses, "trees": trees, "sky": sky}


# Decision 22 (2026-09-03): nothing John asks is dropped. A phrase the fixed fields already hold (a colour,
# a wall, a roof, a garage side, a porch, a storey count, trees, sky) is not a leftover; anything else is
# kept verbatim in "features" (that house) / "other_features" (the grounds) and noted in the gaps ledger.
_HELD = re.compile(r"\b(%s|gable|hip|pitched|garage|porch|stor(e)?ys?|stories|floors?|levels?|trees?|sky|sunset|cloudy|overcast|clear|"
                   r"cul[ -]?de[ -]?sac|straight|street|one|two|three|1|2|3|a|an|the|and|with|on|of|to|in|side|left|right|walls?|houses?|homes?|roofs?|tall|"
                   r"my|this|that|it|will|be|is|are|for|me|please|want|like|build|make)\b"
                   % "|".join(STYLES + WALLS + COLORS + ROOFS), re.I)


def leftovers(items):
    """Strings only, deduped, at most 12 x 80 chars; a phrase made only of words a field holds is dropped."""
    out = []
    for s in items if isinstance(items, list) else []:
        s = " ".join(s.split())[:80] if isinstance(s, str) else ""
        if s and s.lower() not in [o.lower() for o in out] and re.search(r"[a-z]", _HELD.sub("", s), re.I):
            out.append(s)
    return out[:12]


def storeys(h, style):
    """1, 2 or 3: the homeowner's words ('three storeys' in features) win, then the field, then the style's usual."""
    words = " ".join(s for s in (h.get("features") if isinstance(h.get("features"), list) else []) if isinstance(s, str))
    m = re.search(r"\b(one|two|three|1|2|3)[ -]?(stor(e)?ys?|stories|floors?|levels?)\b", words, re.I)
    try: n = int(h.get("stories"))
    except (TypeError, ValueError): n = 0
    if m: n = {"one": 1, "two": 2, "three": 3}.get(m.group(1).lower()) or int(m.group(1))
    return n if n in (1, 2, 3) else (2 if style in ("colonial", "modern", "farmhouse") else 1)


def normalise(b, text="", revise=False, candidates=False):
    # Decision (2026-09-03, John: "tell me what it couldn't use"): a REAL substitution is John's word
    # PRESENT and non-empty and not one this field accepts - a field the model left blank and a default
    # filled is not that, and gets no entry. "used" for house fields is resolved at the bottom, after
    # padding/truncation/the variety guard below have had their say, so it never reports a stale value.
    swapped = []
    layout = "straight" if str(b.get("layout", "")).lower().startswith("str") else "cul-de-sac"
    trees = b.get("trees") if b.get("trees") in ("few", "some", "many") else "some"
    sky = b.get("sky") if b.get("sky") in ("clear", "cloudy", "sunset", "overcast") else "clear"
    for field, raw, allowed, used in (("layout", b.get("layout"), ("cul-de-sac", "straight"), layout),
                                      ("trees", b.get("trees"), ("few", "some", "many"), trees),
                                      ("sky", b.get("sky"), ("clear", "cloudy", "sunset", "overcast"), sky)):
        if isinstance(raw, str) and raw.strip() and raw not in allowed:
            swapped.append({"house": None, "field": field, "asked": raw.strip()[:60], "used": used})
    out = {"name": str(b.get("name") or "New Neighbourhood")[:40], "layout": layout, "trees": trees, "sky": sky,
           "houses": [], "other_features": leftovers(b.get("other_features"))}
    pending = []          # (house, field, asked) - "used" not known yet; resolved below once houses are final
    for h in (b.get("houses") or [])[:8]:
        if not isinstance(h, dict):
            continue
        hi = len(out["houses"]) + 1
        style = h.get("style") if h.get("style") in STYLES else "colonial"
        wall = h.get("wall") if h.get("wall") in WALLS else "brick"
        wall_color = h.get("wall_color") if h.get("wall_color") in COLORS else "natural"
        roof = h.get("roof") if h.get("roof") in ROOFS else "clay"
        garage = h.get("garage") if h.get("garage") in ("left", "right", "none") else "right"
        for field, raw, allowed in (("style", h.get("style"), STYLES), ("wall", h.get("wall"), WALLS),
                                    ("wall_color", h.get("wall_color"), COLORS), ("roof", h.get("roof"), ROOFS),
                                    ("garage", h.get("garage"), ("left", "right", "none"))):
            if isinstance(raw, str) and raw.strip() and raw not in allowed:
                pending.append((hi, field, raw.strip()[:60]))
        out["houses"].append({"style": style, "stories": storeys(h, style), "wall": wall, "wall_color": wall_color,
                              "roof": roof, "garage": garage,
                              "porch": bool(h.get("porch", False)), "features": leftovers(h.get("features"))})
    want = b.get("house_count") if isinstance(b.get("house_count"), int) and 1 <= b.get("house_count") <= 8 else None
    if revise:
        want = len(out["houses"]) or want          # an edit ("make house 1 red") must not re-count the street from its words
    else:
        # the sentence outranks the model's count: "multiple homes" came back as 1 house once (2026-09-02)
        m = re.search(r"\b([1-8])\b", text)
        if m: want = int(m.group(1))
        elif re.search(r"\bcouple\b", text, re.I): want = max(want or 0, 2)
        elif re.search(r"\b(multiple|several|few|some|many|homes|houses)\b", text, re.I): want = max(want or 0, 4)
        elif out["layout"] == "cul-de-sac" and (want or 0) < 3: want = 4        # "build cul de sac" gave ONE house (2026-09-02) - a cul-de-sac is a ring of homes
    if want:
        while len(out["houses"]) < want:                         # the model said 5 but listed 3: repeat with a twist
            src = dict(out["houses"][len(out["houses"]) % max(1, len(out["houses"]))]) if out["houses"] else rules_brief("one home")["houses"][0]
            src["wall_color"] = COLORS[len(out["houses"]) % len(COLORS)]; src["features"] = []      # a padded copy asks for nothing extra
            out["houses"].append(src)
        out["houses"] = out["houses"][:want]
    if not out["houses"]:
        out["houses"] = rules_brief("4 homes")["houses"]
    # "each with a garage" came back as four "none"s (2026-09-03): the sentence outranks the model here too
    if not revise and re.search(r"\bgarages?\b", text, re.I) and all(h["garage"] == "none" for h in out["houses"]):
        for i, h in enumerate(out["houses"]):
            h["garage"] = "right" if i % 2 == 0 else "left"
    # variety guard: a street of five with two styles repeating is not "different homes".
    # NOT on the candidates path (2026-09-04): there the three houses are three takes on ONE house
    # John asked for, so a shared style is the POINT, not a defect. Left on, this guard rewrote
    # candidate 3 of an all-colonial set into a ranch — undoing the prompt fix at the code layer.
    if not candidates:
        seen = {}
        for i, h in enumerate(out["houses"]):
            seen[h["style"]] = seen.get(h["style"], 0) + 1
            if seen[h["style"]] > 2:
                for st in STYLES:
                    if seen.get(st, 0) == 0:
                        h["style"] = st; seen[st] = 1; seen[h["style"]] = seen.get(h["style"], 1)
                        h["roof"] = {"colonial": "clay", "ranch": "ceramic", "modern": "flat",
                                     "cottage": "metal", "farmhouse": "metal", "georgian": "clay"}.get(st, "shingle")
                        h["porch"] = st in ("cottage", "farmhouse")
                        break
    for house, field, asked in pending:               # now that houses are final: a house dropped by truncation reports nothing
        if house <= len(out["houses"]):
            swapped.append({"house": house, "field": field, "asked": asked, "used": out["houses"][house - 1][field]})
    out["house_count"] = len(out["houses"])
    out["swapped"] = swapped
    return out


def couldnt_sentence(swapped, unbuilt):
    """One factual, plain-English line combining the swap ledger (normalise's "swapped") and the
    unbuilt-feature ledger (build-neighbourhood.py's UNBUILT, via status.json "unbuilt_features") -
    what John asked for that was not on any list, and what he asked for that nothing here can build
    yet. None (never a cheerful "") when both are empty. Never apologises, never pads."""
    swapped, unbuilt = swapped or [], unbuilt or []
    if not swapped and not unbuilt:
        return None
    bits = []
    for s in swapped:
        place = "house %s's %s" % (s["house"], s["field"]) if s.get("house") else "the %s" % s["field"]
        bits.append('you asked for "%s" - %s is "%s" instead' % (s["asked"], place, s["used"]))
    if unbuilt:
        bits.append("could not build: " + ", ".join(u["phrase"] for u in unbuilt))
    return "; ".join(bits) + "."


def write_brief(text, current=None):
    try:
        b, source = ollama_brief(text, current)
    except Exception as e:
        log("brief writer: no model answered (%s) - word rules" % e)
        b = current or rules_brief(text); source = "word-rules (no model answered)"
    b = normalise(b, text, revise=current is not None); b["source"] = source; b["request"] = text
    if current is not None:
        b["revised_from"] = current.get("request", "")
    return b


WORLDS = r"C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\worlds"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def place_brief(slug):
    """The latest version's brief of an existing place (its 0-world.json carries it)."""
    if not _SLUG.match(slug or ""): raise RuntimeError("bad place name")
    wd = os.path.join(WORLDS, slug, "output", "world")
    if not os.path.isdir(wd): raise RuntimeError("no such place: %s" % slug)
    idx = sorted(int(f.split("-")[0]) for f in os.listdir(wd) if re.match(r"^\d+-world\.json$", f))
    if not idx: raise RuntimeError("%s has no world file to build on" % slug)
    man = json.load(open(os.path.join(wd, "%d-world.json" % idx[-1]), encoding="utf-8"))
    brief = man.get("brief")
    if not isinstance(brief, dict): raise RuntimeError("%s was not built by the Neighbourhood Builder (no brief to edit)" % slug)
    return brief, idx[-1]


# ------------------------------------------------------------------ candidates (2026-09-03, John: "pictures first, then I choose")
CANDIDATES_SYSTEM = ("You design houses for a homeowner. From the instruction, propose THREE candidates that are the SAME house rendered three ways, "
                     "not three different houses. " + TEMPLATE +
                     '\nWhatever the instruction fixes - "style", "stories", "wall", "wall_color", "roof", "porch", or which side "garage" is on - must '
                     'be IDENTICAL across houses[0], houses[1] and houses[2]; never vary a field the instruction named, even to make the candidates '
                     'look different. Vary only what the instruction leaves unspecified, and failing that only fine interpretive detail (proportion, '
                     'spacing, trim, or a different shade within the named wall_color) that no field captures. '
                     'Every phrase from the instruction that no field can hold goes into that house\'s "features" (or the street\'s "other_features"), '
                     'and the same "features" / "other_features" entries must appear in ALL THREE of houses[0], houses[1] and houses[2] - not only the '
                     'first candidate; this is a hard requirement. '
                     '\nAlways: "layout": "straight", "house_count": 3, exactly three entries in "houses", "name": "Candidates".')


# A PHOTO with the order (2026-09-03, John pasted a red-brick Georgian with a columned portico):
# a vision model reads the photo into ONE order-form house; candidate 1 is that house, 2 and 3
# vary around it.
# CORRECTED 2026-09-04: the line that used to sit here said "the kit still cannot make columns or
# a pediment". That is stale and was steering decisions — build-neighbourhood.py's feat_columns()
# (395-412) and feat_pediment() (414-422) build both today, plus dormers, chimneys, a balcony and
# shutters. Read those functions before believing any comment about what the kit cannot do.
VISION_PREFIXES = ("qwen3-vl", "qwen2.5vl", "qwen2-vl", "minicpm-v", "ibm/granite3.3-vision", "llava", "llama3.2-vision")   # John's garage 2026-09-03: qwen3-vl:8b, qwen2.5vl:7b, minicpm-v, granite3.3-vision:2b
VISION_SYSTEM = ("Look at the photo of a house. Describe THAT house as one order-form entry. " + TEMPLATE +
                 '\nReply with the form for a 1-house straight street: "house_count": 1, exactly one entry in "houses", '
                 'matching the photo as closely as the allowed values permit. COUNT what is actually in the photo - '
                 'storeys, columns, dormers, chimneys - and use those numbers. Put the count into the feature words too '
                 '("four white columns", "two chimneys", "two dormers"), because the builder reads a number out of that '
                 'phrase. What you see that no field holds goes into "features".')
# 2026-09-04: the worked example that used to live in the line above ("a columned brick manor =
# colonial, brick, red, 2 stories, porch true") was pinning every photographed manor to colonial —
# and STYLE["colonial"] forces roof="gable" (build-neighbourhood.py:43), so a hipped roof in a photo
# had no path to survive. It also anchored storeys at 2 for a house that might be 3. Removed.


def vision_house(image_path, text):
    """One house read off the photo by a local vision model, or None when no vision model answers."""
    try:
        b64 = base64.b64encode(open(image_path, "rb").read()).decode("ascii")
    except Exception as e:
        log("vision: cannot read %s (%s)" % (image_path, e)); return None
    tags = [t for t in garage() if t.split(":")[0].startswith(VISION_PREFIXES)]
    for tag in tags:
        try:
            body = {"model": tag, "stream": False, "format": "json", "options": {"temperature": 0.1},
                    "messages": [{"role": "user", "content": VISION_SYSTEM + "\nThe homeowner said: " + text, "images": [b64]}]}
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                content = json.loads(r.read())["message"]["content"].strip()
            raw = json.loads(content[content.find("{"):content.rfind("}") + 1])
            houses = normalise(tolerant(raw), "1 house", revise=True)["houses"]
            if houses:
                log("vision (%s): %s" % (tag, json.dumps(houses[0])))
                return houses[0]
        except Exception as e:
            log("vision lane %s failed: %s" % (tag, str(e)[:200]))
    log("vision: no vision model in the garage answered (%s)" % ", ".join(tags) if tags else "vision: no vision model installed")
    return None


def candidates_brief(text, n=3, image=None):
    """A 3-house straight street whose houses are three takes on the order — rendered, never built."""
    ref = vision_house(image, text) if image else None
    system = CANDIDATES_SYSTEM
    if ref:
        system += ("\nREFERENCE HOUSE read from the homeowner's photo: " + json.dumps(ref) +
                   " — houses[0] must be exactly this; houses[1] and houses[2] keep its style and stories and vary only wall_color, roof or porch.")
    try:
        errors = []
        for tag in pick_models(text):
            try:
                raw = ask(tag, system, text); b = tolerant(raw); source = tag; break
            except Exception as e:
                errors.append("%s: %s" % (tag, str(e)[:120])); log("candidates lane %s failed: %s" % (tag, str(e)[:200]))
        else:
            raise RuntimeError("; ".join(errors) or "no model in the garage")
    except Exception as e:
        log("candidates: no model answered (%s) - word rules" % e)
        b = rules_brief(text); source = "word-rules (no model answered)"
    b["layout"] = "straight"; b["house_count"] = n
    b = normalise(b, "%d houses" % n, revise=False, candidates=True)
    if len(b["houses"]) > n: b["houses"] = b["houses"][:n]; b["house_count"] = n
    if ref:
        b["houses"][0] = ref                      # the photo's house is always candidate 1, whatever the model did with it
        b["reference_house"] = ref
    b["name"] = "Candidates"; b["source"] = source; b["request"] = text; b["preview"] = True
    return b


# ------------------------------------------------------------------ the gaps ledger (Decision 22, tools/capability-gaps.CONTRACT.md section 1)
GAPS = r"C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\tools\capability-gaps.jsonl"
# the house features build-neighbourhood.py makes itself (its FEATURES table) — never gaps
BUILDER_MAKES = re.compile(r"\b(columns?|pillars?|portico|colonnade|pediments?|dormers?|chimneys?|balcon(y|ies)|shutters?)\b", re.I)


def note_gaps(jid, brief, base, current=None):
    """Every phrase the order form could not hold becomes one JSON line in the capability-gaps ledger -
    append-only, never rewritten; the gap router turns each into work. Not written twice: a phrase the
    place already carried before this sentence (`current`, the brief being revised) was noted when it was
    asked, and a line whose id is already there (the same sentence re-posted: the chosen house, 'more'
    candidates) is skipped. Returns the phrases written this time; a ledger fault never stops a build."""
    text = str(brief.get("request", ""))
    carried = {p.lower() for p in (current or {}).get("other_features") or []}
    for h in (current or {}).get("houses") or []:
        carried |= {p.lower() for p in h.get("features") or []}
    # 2026-09-03 19:58, first live order: the builder BUILT the columns, portico, dormers and chimneys
    # itself, and the ledger sent the same four words to the factory as "things" — four wasted prop
    # jobs. A feature the builder's own helpers make (build-neighbourhood.py FEATURES) is an ability it
    # HAS; only what no helper knows is a gap. The builder reports what it could not make per job
    # (status.json unbuilt_features) — that, not the wish list, is what the ledger should carry.
    rows = [("grounds", None, p) for p in brief.get("other_features") or [] if p.lower() not in carried]
    for i, h in enumerate(brief.get("houses") or []):
        rows += [("house", "H%d" % (i + 1), p) for p in h.get("features") or [] if p.lower() not in carried and not BUILDER_MAKES.search(p)]
    if not rows:
        return []
    seen, written = set(), []
    try:
        for line in open(GAPS, encoding="utf-8"):
            try: seen.add(json.loads(line).get("id"))
            except ValueError: pass
    except OSError:
        pass
    at = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with open(GAPS, "a", encoding="utf-8") as f:
            for target, house, phrase in rows:
                gid = hashlib.sha1(("neighbourhood-builder" + text + phrase).encode("utf-8")).hexdigest()[:12]
                if gid in seen: continue
                seen.add(gid)
                f.write(json.dumps({"id": gid, "at": at, "source": "neighbourhood-builder", "session": jid, "request": text, "phrase": phrase,
                                    "context": {"target": target, "world": base, "version": None, "house": house}, "status": "new"}, ensure_ascii=False) + "\n")
                written.append(phrase)
    except OSError as e:
        log("gaps ledger write failed (%s): %s" % (GAPS, e))
    if written:
        log("gaps noted for %s: %s" % (jid, ", ".join(written)))
    return written


# ------------------------------------------------------------------ jobs
def start_job(text, base=None, house=None, preview=False, image=None):
    """A build (fresh, or the next version of `base`), a candidates PREVIEW (pictures only), or —
    with `house` — the deterministic build of a house John chose on the garage wall (no model)."""
    if BLENDER is None:
        raise RuntimeError("UPBGE not found. Looked in: " + " | ".join(BLENDER_CANDIDATES))
    with _lock:
        cur = _current["job"]
        if cur and job_status(cur).get("status") == "building":
            raise RuntimeError("a build is already running (%s) - wait for it" % cur)
        current = None
        if base:
            current, _ = place_brief(base)
        if preview:
            brief = candidates_brief(text, image=image if image and os.path.isfile(image) else None)
        elif house is not None:
            if current is None: raise RuntimeError("a chosen house needs the place it joins (base)")
            brief = json.loads(json.dumps(current))
            brief["houses"] = list(brief.get("houses", [])) + [house]
            brief = normalise(brief, text, revise=True)
            brief["source"] = "chosen on the garage wall"; brief["request"] = text; brief["revised_from"] = current.get("request", "")
        else:
            brief = write_brief(text, current)
        jid = time.strftime("%Y%m%d-%H%M%S")
        jd = os.path.join(JOBS, jid); os.makedirs(jd, exist_ok=True)
        json.dump(brief, open(os.path.join(jd, "brief.json"), "w", encoding="utf-8"), indent=1)
        json.dump({"status": "building", "stage": "starting UPBGE", "images": [], "base": base, "preview": preview}, open(os.path.join(jd, "status.json"), "w"))
        cmd = [BLENDER, "--background", "--factory-startup", "-noaudio", "--python", os.path.join(HERE, "run-brief.py"), "--", jd] \
            + (["--preview"] if preview else (["--slug", base] if base else []))
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = open(os.path.join(jd, "upbge-console.txt"), "w", encoding="utf-8")
        subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, creationflags=flags, cwd=HERE)
        _current["job"] = jid
        log("job %s%s%s: %d houses, %s, sky %s (brief by %s)" % (jid, " PREVIEW" if preview else "", " on " + base if base else "", brief["house_count"], brief["layout"], brief["sky"], brief["source"]))
        brief["gaps"] = note_gaps(jid, brief, base, current)      # in the reply only (brief.json stays the pure order form): what was noted for the workshop this time
        return jid, brief


def job_status(jid):
    jd = os.path.join(JOBS, jid)
    try:
        st = json.load(open(os.path.join(jd, "status.json"), encoding="utf-8"))
    except Exception:
        st = {"status": "unknown", "images": []}
    try:
        st["brief"] = json.load(open(os.path.join(jd, "brief.json"), encoding="utf-8"))
    except Exception:
        pass
    try:
        st["log_tail"] = open(os.path.join(jd, "build-log.txt"), encoding="utf-8").read()[-1500:]
    except Exception:
        st["log_tail"] = ""
    st["job"] = jid
    st["images"] = ["/jobs/%s/%s" % (jid, i) for i in st.get("images", [])]
    st["couldnt"] = couldnt_sentence((st.get("brief") or {}).get("swapped"), st.get("unbuilt_features"))
    return st


def list_jobs():
    if not os.path.isdir(JOBS):
        return []
    return sorted([d for d in os.listdir(JOBS) if os.path.isdir(os.path.join(JOBS, d))], reverse=True)[:20]


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Neighbourhood Builder</title>
<style>
body{margin:0;font:15px system-ui,Segoe UI,sans-serif;background:#0f1115;color:#e6e6e6;display:grid;grid-template-columns:380px 1fr;height:100vh}
aside{padding:18px;border-right:1px solid #262a33;overflow:auto}main{padding:18px;overflow:auto}
h1{font-size:18px;margin:0 0 12px}textarea{width:100%;height:96px;background:#171a21;color:#eee;border:1px solid #333;border-radius:8px;padding:10px;font:inherit;box-sizing:border-box}
button{margin-top:8px;width:100%;padding:10px;border:0;border-radius:8px;background:#8ad3b0;color:#0b1a12;font-weight:600;cursor:pointer}button:disabled{opacity:.5}
.st{margin:14px 0;color:#9aa4b2;white-space:pre-wrap}.house{background:#171a21;border-radius:8px;padding:8px 10px;margin:6px 0;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}.grid img{width:100%;border-radius:8px;background:#000}
.cap{font-size:12px;color:#9aa4b2;margin:4px 0 0}.hist a{color:#8ad3b0;display:block;font-size:12px;margin:3px 0}
</style></head><body>
<aside><h1>Neighbourhood Builder</h1>
<textarea id="t" placeholder="e.g. build a cul-de-sac with multiple homes, one of them a red brick colonial, evening light"></textarea>
<button id="b" onclick="go()">Build it</button>
<div class="st" id="s">UPBGE builds it in the background. Pictures land here in a minute or two.</div>
<div id="houses"></div>
<div class="hist" id="hist"></div></aside>
<main><div class="grid" id="g"></div></main>
<script>
let job=null, timer=null;
async function go(){const text=document.getElementById('t').value.trim(); if(!text)return;
 document.getElementById('b').disabled=true; document.getElementById('s').textContent='Writing the order form...';
 const r=await fetch('/api/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
 const j=await r.json(); if(!r.ok){document.getElementById('s').textContent='Could not start: '+(j.error||r.status); document.getElementById('b').disabled=false; return;}
 job=j.job; show(j); poll();}
function show(st){ if(st.brief){const b=st.brief; document.getElementById('houses').innerHTML='<div class="house"><b>'+b.name+'</b> - '+b.layout+', '+b.house_count+' houses, '+b.trees+' trees, '+b.sky+' sky<br><small>order form by '+(b.source||'')+'</small></div>'+
   (b.houses||[]).map((h,i)=>'<div class="house">H'+(i+1)+': '+h.style+', '+h.wall_color+' '+h.wall+', '+h.roof+' roof'+(h.garage!=='none'?', garage '+h.garage:'')+(h.porch?', porch':'')+'</div>').join('');}
 const stage=st.stage||st.status||''; document.getElementById('s').textContent=(st.status==='failed'?'FAILED: '+(st.error||''):'Status: '+stage)+(st.fallbacks&&st.fallbacks.length?'\\nFallbacks: '+st.fallbacks.join('; '):'');
 document.getElementById('g').innerHTML=(st.images||[]).map(u=>'<div><img src="'+u+'"><div class="cap">'+u.split('/').pop()+'</div></div>').join('');}
async function poll(){ if(!job)return; const r=await fetch('/api/job/'+job); const st=await r.json(); show(st);
 if(st.status==='done'||st.status==='failed'){document.getElementById('b').disabled=false; hist(); return;} timer=setTimeout(poll,3000);}
async function hist(){const r=await fetch('/api/jobs'); const j=await r.json(); document.getElementById('hist').innerHTML='<br>Earlier builds:'+j.map(x=>'<a href="#" onclick="job=\\''+x+'\\';poll();return false;">'+x+'</a>').join('');}
hist();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if p == "/api/health":
            ok = BLENDER is not None
            return self.send(200, {"ok": ok, "upbge": BLENDER, "model": (pick_models("") or [MODEL])[0], "lane": pick_models("")[:3], "current_job": _current["job"]})
        if p == "/api/jobs":
            return self.send(200, list_jobs())
        if p == "/api/models":
            tags = garage()
            return self.send(200, {"garage": tags, "lane": pick_models(""), "cloud": [t for t in tags if is_cloud(t)],
                                   "local": [t for t in tags if not is_cloud(t)], "law": "cloud for the thinking (prepaid), the 4090 stays free for UPBGE"})
        if p.startswith("/api/job/"):
            return self.send(200, job_status(os.path.basename(p)))
        if p.startswith("/jobs/"):
            parts = p.split("/")
            if len(parts) == 4 and ".." not in p:
                f = os.path.join(JOBS, parts[2], parts[3])
                if os.path.isfile(f):
                    ctype = {"png": "image/png", "json": "application/json", "txt": "text/plain", "blend": "application/octet-stream"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
                    return self.send(200, open(f, "rb").read(), ctype)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        # /api/build       {text, base?}            a build, or the next version of `base`
        # /api/build       {text, base, house}      the house John chose on the garage wall — no model, appended as-is
        # /api/candidates  {text}                   three takes on the order, rendered as pictures only (--preview)
        if self.path not in ("/api/build", "/api/candidates"):
            return self.send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            text = str(body.get("text", "")).strip(); base = str(body.get("base") or "").strip() or None
            if not text:
                return self.send(400, {"error": "say what you want built"})
            house = body.get("house") if isinstance(body.get("house"), dict) else None
            preview = self.path == "/api/candidates"
            image = str(body.get("image") or "").strip() or None          # a photo John pasted into V17 (absolute path)
            jid, brief = start_job(text, base, house=house, preview=preview, image=image)
            return self.send(200, {"job": jid, "brief": brief, "status": "building", "base": base, "preview": preview,
                                   "couldnt": couldnt_sentence(brief.get("swapped"), None)})
        except Exception as e:
            return self.send(409 if "already running" in str(e) else 500, {"error": str(e)})


if __name__ == "__main__":
    os.makedirs(JOBS, exist_ok=True)
    log("Neighbourhood Builder on http://127.0.0.1:%d/  UPBGE: %s  model: %s" % (PORT, BLENDER or "NOT FOUND", MODEL))
    class OneOnly(ThreadingHTTPServer):
        allow_reuse_address = False   # on Windows the default let TWO copies listen on 8196 at once (seen 2026-09-02); now a second start fails loudly
    try:
        srv = OneOnly(("127.0.0.1", PORT), H)
    except OSError as e:
        log("could not take port %d - is the Neighbourhood Builder already running? (%s)" % (PORT, e)); sys.exit(1)
    srv.serve_forever()
