"""Audits the generated deck: block structure, request bodies, variables set before use, button
references, layout overlap and the persistence the shared apply button relies on. build_deck.py runs it
after every build; run it alone with  python3 tools/audit_deck.py"""
import json
import pathlib
import re
import sys

DECK = pathlib.Path(__file__).resolve().parent.parent / "deck" / "HueScenes.deck.json"


def audit(w):
    """Returns a list of problems in the deck wrapper `w`; empty means it passed."""
    deck = json.loads(w["deck_data"])
    B = deck["button_list"]
    issues = []
    def bad(bid, msg): issues.append(f"[{bid}] {msg}")

    KNOWN = {6,7,9,11,15,20,66,78,79,83,91,100,126,127,132,133,137,141,142,153,162,168,169,190,214,227,255,306}
    OPS = {"==","!=","<",">","<=",">="}
    SAVE_BOX = {15:0,20:0,66:0,79:0,83:0,91:0,100:1,127:3,162:2,168:0,169:4,214:2,306:1}
    ids = [b["button_id"] for b in B]
    if len(ids) != len(set(ids)): bad("deck", "duplicate button ids")
    groups = {b.get("group_id") for b in B if b.get("group_id")}

    # layout overlap
    for i, a in enumerate(B):
        for b in B[i+1:]:
            if a["x"] < b["x"]+b["width"]-1e-9 and b["x"] < a["x"]+a["width"]-1e-9 and a["y"] < b["y"]+b["height"]-1e-9 and b["y"] < a["y"]+a["height"]-1e-9:
                bad(a["button_id"], f"overlaps {b['button_id']}")

    GLOBAL_OK = {"global"}
    for b in B:
        bid, cl = b["button_id"], b["command_list"]
        fn = int(b["functions"])
        if bool(cl) != bool(fn & 1): bad(bid, "functions bit 1 vs commands")
        if bool(b["triggers"]) != bool(fn & 16): bad(bid, "functions bit 16 vs triggers")
        if bool(b["persistent"]) != bool(fn & 64): bad(bid, "functions bit 64 vs persistent")
        if bool(b["queueable"]) != bool(fn & 128): bad(bid, "functions bit 128 vs queueable")
        for t in b["triggers"]:
            if t.get("button_id") != bid: bad(bid, "trigger button_id mismatch")
        # positions
        for i, c in enumerate(cl):
            if c.get("pos") != float(i): bad(bid, f"pos {c.get('pos')} at index {i}")
            if int(c["cmd"]) not in KNOWN: bad(bid, f"unknown cmd {c['cmd']} at {i}")
        # block structure: every block must fit inside its parent
        stack = []  # (end_index_exclusive, cmd, left operand)
        setter = {}  # variable -> cmd that last set it
        for i, c in enumerate(cl):
            while stack and i >= stack[-1][0]: stack.pop()
            k = int(c["cmd"])
            if k == 11 and not any(s[1] == 9 for s in stack): bad(bid, f"Break at {i+1} not inside a Repeat")
            # A path read from a bridge reply (a.b...) crashes Array Get Size when it is missing, so it must be guarded.
            if k == 100 and "." in c.get("b0", ""):
                guards = [s for s in stack if s[1] == 7]
                if not guards or setter.get(guards[-1][2]) != 91:
                    bad(bid, f"Array Get Size `{c['b0']}` at {i+1} is not guarded by a String Position check of the reply")
            if k == 91: setter[c.get("b0", "")] = 91
            elif k in SAVE_BOX: setter[c.get(f"b{SAVE_BOX[k]}", "")] = k
            if k in (7, 9):
                n = int(c.get("v0", 0)) + (int(c.get("v1", 0)) if k == 7 else 0)
                end = i + 1 + n
                if end > len(cl): bad(bid, f"block at {i+1} runs past the end")
                if stack and end > stack[-1][0]: bad(bid, f"block at {i+1} overruns its parent")
                stack.append((end, k, c.get("b0", "")))
            if k in (7, 11):
                if c.get("b1") not in OPS: bad(bid, f"bad operator {c.get('b1')!r} at {i+1}")
                if k == 7 and int(c.get("v2", 0)) != 1: bad(bid, f"If at {i+1} has v2={c.get('v2')}")
        # async pattern: Command Line saving to resp etc. should be followed by a wait unless intentional
        # requests: substitute variables and validate -d JSON
        for i, c in enumerate(cl):
            if int(c["cmd"]) != 306: continue
            cmdline = c["b0"]
            if c.get("async") != 1.0: bad(bid, f"Command Line at {i+1} without async")
            m = re.search(r' -d "(.*)"$', cmdline)
            if m:
                body = m.group(1).replace('\\"', '"')
                # string-valued vars inside quotes -> placeholder; bare vars -> number
                body2 = re.sub(r'"[^"]*?/\$[^$"]+\$/[^"]*?"(?=\s*[,}\]:])', '"x"', body)
                body2 = re.sub(r'/\$[^$]+\$/', '1', body2)
                try: json.loads(body2)
                except Exception as e: bad(bid, f"invalid JSON body at {i+1}: {body} ({e})")
            if cmdline.count('"') % 2: bad(bid, f"unbalanced quotes at {i+1}: {cmdline[:80]}")
            if "curl" in cmdline and "-X PUT" in cmdline and "Content-Type" not in cmdline: bad(bid, f"PUT without content type at {i+1}")
        # variables: used before set (within the button, in order; loop bodies make this approximate)
        setv = set(["global"])
        for i, c in enumerate(cl):
            k = int(c["cmd"])
            texts = [v for kk, v in c.items() if re.fullmatch(r"b\d+", kk) and isinstance(v, str)]
            for t in texts:
                for v in re.findall(r"/\$([A-Za-z_]\w*)", t):
                    if v not in setv: bad(bid, f"/${v}$/ used before set at {i+1}")
            if k in (7, 11):
                for box in ("b0", "b2"):
                    v = c.get(box, "")
                    if re.fullmatch(r"[A-Za-z_]\w*", v) and v not in setv: bad(bid, f"yellow `{v}` used before set at {i+1}")
            if k in (9, 190):
                v = c.get("b0", "")
                if re.fullmatch(r"[A-Za-z_]\w*", v) and v not in setv: bad(bid, f"`{v}` (count/ms) used before set at {i+1}")
            if k == 15:
                for v in re.findall(r"\b([A-Za-z_]\w*)\b", c.get("b2", "")):
                    if v not in setv and not re.fullmatch(r"\d+", v): bad(bid, f"`{v}` in expression used before set at {i+1}")
            if k in SAVE_BOX:
                name = c.get(f"b{SAVE_BOX[k]}", "")
                if name: setv.add(name.split(".")[0])
        # references to other buttons
        for i, c in enumerate(cl):
            k = int(c["cmd"])
            if k == 132 and "/$" not in c["b0"] and c["b0"] not in ids: bad(bid, f"Trigger Button to missing `{c['b0']}` at {i+1}")
            if k == 133 and c["b0"] not in ids and c["b0"] not in groups and c["b0"] != "all": bad(bid, f"Stop Button to missing `{c['b0']}` at {i+1}")
            if k == 132 and c["b0"] == bid and not c.get("dis"): bad(bid, f"triggers itself at {i+1}")
        # action buttons must persist for Get Button Variable
    for b in B:
        if any(int(c["cmd"]) == 132 and c["b0"] == "hueApply" for c in b["command_list"]) and not b["persistent"]:
            bad(b["button_id"], "calls hueApply but is not persistent")
    # sequence defaults point at real buttons
    seq = next(b for b in B if b["button_id"] == "hueSequence")
    for c in seq["command_list"]:
        if int(c["cmd"]) == 20 and c["b0"] in ("step1Button", "step2Button", "endButton") and c["b1"] and c["b1"] not in ids:
            bad("hueSequence", f"{c['b0']} default `{c['b1']}` is not a button")
    return issues


if __name__ == "__main__":
    wrapper = json.loads(DECK.read_text(encoding="utf-8"))
    found = audit(wrapper)
    print("\n".join(found) if found else "deck audit: no issues")
    sys.exit(1 if found else 0)
