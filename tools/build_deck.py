#!/usr/bin/env python3
"""Build the "Hue Scenes" SAMMI deck: any SAMMI trigger -> a Philips Hue scene, color or white.

Outputs
  deck/HueScenes.deck.json   - paste this into SAMMI (side menu > Paste Deck)
  deck/HueScenes.commands.md - human-readable listing of every button and command

Format notes (command ids, field layout, block encoding, trigger keys) are in
docs/SAMMI deck JSON format notes.md. Run:  python3 tools/build_deck.py
"""
import json
import re
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "deck"

INI = "hue_scenes.ini"
LIST_FILE = "hue_scenes_list.txt"   # the pick lists are written here and opened in Notepad (SAMMI's popups do not scroll)      # relative to the SAMMI folder
SEC = "hue"                # [hue] section: ip, key, light
SAMMI_MIN_VERSION = "2024.2.0"
DECK_NAME = "Hue Scenes"
GRID_X, GRID_Y = 8, 8      # cell = 0.125 x 0.125, exact in binary so SAMMI's overlap check cannot misfire

CURL = "curl.exe -sk -m 8"  # -s quiet, -k accept bridge cert, -m 8 second timeout
AUTH = '-H "hue-application-key: /$hueKey$/" -H "Content-Type: application/json"'
LIGHT_URL = '"https:///$hueIp$//clip/v2/resource//$hueLightType$///$hueLightId$/"'   # light or grouped_light
SCENE_URL = '"https:///$hueIp$//clip/v2/resource/scene//$hueSceneId$/"'

# BGR decimal button colors (GameMaker convention)
def bgr(r, g, b):
    return float(b * 65536 + g * 256 + r)

GRAY, RED, BLUE, WARM, DARK, TEAL = bgr(192, 192, 192), bgr(220, 40, 40), bgr(40, 80, 220), bgr(255, 200, 120), bgr(70, 70, 70), bgr(40, 160, 160)


# ----------------------------------------------------------------------------
# command helpers: each returns a dict, or a Block for statements
# ----------------------------------------------------------------------------
BASE = dict(obsid="Main", vis=1.0, ms=0.0, sel=False, dis=0.0, xpan=0.0)


def cmd(cid, **kw):
    d = dict(BASE)
    d["cmd"] = float(cid)
    d.update(kw)
    return d


def comment(text, color=1):            return cmd(6, b0=text, v0=float(color))
def alert(msg):                        return cmd(142, b0=msg)
def popup(msg, pause=True):            return cmd(141, b0=msg, v0=1.0 if pause else 0.0)
def delete_var(name):                  return cmd(78, b0=name)
def shell(command, save=""):           return cmd(306, b0=command, b1=save, **{"async": 1.0})
def wait_exists(var, ms):              return cmd(153, b0=var, b1=str(ms))
def wait_ms(ms):                       return cmd(190, b0=str(ms))
def parse(name, json_str):             return cmd(168, b0=name, b1=json_str)
def set_local(name, value, op="="):    return cmd(15, b0=name, b1=op, b2=value)
def set_string(name, text, rel=False): return cmd(20, b0=name, b1=text, v0=bool(rel))
def str_pos(save, string, search, ci=False): return cmd(91, b0=save, b1=string, b2=search, b3="0", v0=bool(ci))  # v0 = case insensitive
def str_len(save, string):             return cmd(83, b0=save, b1=string)
def file_append(path, text):           return cmd(255, b0=path, b1=text)
def file_delete(path):                 return cmd(227, b0=path)
def ini_save(key, text):               return cmd(126, b0=INI, b1=SEC, b2=key, b3=text)
def ini_load(key, save):               return cmd(127, b0=INI, b1=SEC, b2=key, b3=save)
def wait_input(msg, default, save):    return cmd(214, b0=msg, b1=default, b2=save)
def str_to_num(save, src):             return cmd(79, b0=save, b1=src)
def arr_size(arr, save):               return cmd(100, b0=arr, b1=save)
def overtime(ms):                      return cmd(137, b0=str(ms))
def http(url, method, header_obj, body, save):
    return cmd(169, b0=url, b1=method, b2=header_obj, b3=body, b4=save)
def trigger_button(bid, delay_ms, disabled=False, queueable=False):
    c = cmd(132, b0=bid, b1=str(delay_ms), v0=bool(queueable))
    c["dis"] = 1.0 if disabled else 0.0
    return c


class Block:
    """A statement (If / Repeat) with nested children. v0 = flattened block size."""
    def __init__(self, head, body, else_body=()):
        self.head, self.body, self.else_body = head, list(body), list(else_body)


def if_(left, op, right, then, else_=()):
    head = cmd(7)
    for k in range(60):                      # SAMMI stores 20 condition slots
        head[f"b{k}"] = "==" if k % 3 == 1 else ""
    for k in range(3, 23):
        head[f"v{k}"] = 0.0
    head.update(b0=left, b1=op, b2=right, v2=1.0)   # v2 = number of conditions
    return Block(head, then, else_)


def repeat(count, body):
    return Block(cmd(9, b0=count), body)


def trigger_pull(save, key):            return cmd(66, b0=save, b1=key)
def get_button_var(bid, name, save):   return cmd(162, b0=bid, b1=name, b2=save)


def break_if(left, op, right):
    """Break (11): leaves the enclosing Repeat when the condition holds. Same boxes as If."""
    return cmd(11, b0=left, b1=op, b2=right, v0=0.0)


def stop_button(bid, ongoing=True, queued=True, include_self=False):
    """Stop Button/Group (133): stops a button or every button in a group (`bid` may be a group id)."""
    return cmd(133, b0=bid, v0=float(ongoing), v1=float(queued), v2=float(include_self))


def flatten(items):
    out = []
    for it in items:
        if isinstance(it, Block):
            body, els = flatten(it.body), flatten(it.else_body)
            head = dict(it.head)
            head["v0"] = float(len(body))
            if els or head["cmd"] == 7.0:
                head["v1"] = float(len(els))
            out.append(head)
            out.extend(body)
            out.extend(els)
        else:
            out.append(dict(it))
    return out


def number(cmds):
    for i, c in enumerate(cmds):
        c["pos"] = float(i)
    return cmds


# ----------------------------------------------------------------------------
# Hue helpers
# ----------------------------------------------------------------------------
def cmd_json(obj):
    """JSON body escaped for a cmd.exe double-quoted -d argument."""
    return json.dumps(obj, separators=(",", ":")).replace('"', '\\"')


def put_light(body):
    return f'{CURL} -X PUT {LIGHT_URL} {AUTH} -d "{cmd_json(body)}"'


def _vars_body(obj):
    """Like cmd_json, but any string value written as @name@ becomes a bare /$name$/
    variable reference (a JSON number once SAMMI substitutes it)."""
    esc = cmd_json(obj)
    return re.sub(r'\\"@(\w+)@\\"', r'/$\1$/', esc)


def put_light_vars(body_vars):
    return f'{CURL} -X PUT {LIGHT_URL} {AUTH} -d "{_vars_body(body_vars)}"'


FADE_MS = "300"   # every change fades over this many milliseconds

# Names accepted by `value` for action color / white.
COLORS = [("red", "0.6915", "0.3083"), ("orange", "0.6", "0.38"), ("yellow", "0.46", "0.47"),
          ("green", "0.17", "0.7"), ("cyan", "0.17", "0.34"), ("blue", "0.1532", "0.0475"),
          ("purple", "0.2725", "0.1096"), ("pink", "0.45", "0.25")]
WHITES = [("warm", "370"), ("neutral", "250"), ("cool", "153")]
EFFECTS = "candle, fire, prism, sparkle, opal, glisten, underwater, cosmos, sunbeam, enchant"


def send(command):
    return [delete_var("resp"), shell(command, "resp"), wait_exists("resp", 10000)]


def check_reply(no_reply_hint):
    return [
        str_len("respLen", "/$resp$/"),
        if_("respLen", "==", "0", [alert(f"Hue: no reply from the bridge ({no_reply_hint}). Run Hue 1: Discover, then Hue 4: Test.")]),
        str_pos("errPos", "/$resp$/", '"description"'),
        if_("errPos", ">", "0", [alert("Hue rejected the request: /$resp$/")]),
    ]


RECALL = f'{CURL} -X PUT {SCENE_URL} {AUTH} -d "{_vars_body({"recall": {"action": "active", "duration": "@fadeMs@"}})}"'
COLOR_BODY = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"},
              "color": {"xy": {"x": "@colorX@", "y": "@colorY@"}}, "dynamics": {"duration": "@fadeMs@"}}
WHITE_BODY = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"},
              "color_temperature": {"mirek": "@whiteMirek@"}, "dynamics": {"duration": "@fadeMs@"}}
ON_BODY = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"}, "dynamics": {"duration": "@fadeMs@"}}
EFFECT_BODY = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"}, "effects": {"effect": "/$value$/"}}
OFF = put_light({"on": {"on": False}})
STOP_EFFECT = put_light({"effects": {"effect": "no_effect"}})
BREATHE = put_light({"alert": {"action": "breathe"}})

# Signals are offered by 'Hue: Try Action' only.
C1 = {"xy": {"x": "@colorX@", "y": "@colorY@"}}
C2 = {"xy": {"x": "@colorX2@", "y": "@colorY2@"}}


def signal_body(colors):
    """Hue's signaling takes no colors for on_off, one for on_off_color and two for alternating."""
    body = {"signal": "/$signal$/", "duration": "@signalMs@"}
    if colors:
        body["colors"] = colors
    return {"signaling": body}


def send_signal():
    return [
        if_("signal", "==", '"on_off_color"', send(put_light_vars(signal_body([C1]))), [
            if_("signal", "==", '"alternating"', send(put_light_vars(signal_body([C1, C2]))),
                send(put_light_vars(signal_body([])))),
        ]),
    ]


LOOKS = "scene, color, white, on, off, none"
EFFECT_CHOICES = f"none, breathe, {EFFECTS}, stop"


def action_settings(look, look_value, brightness, effect, pulses, speed):
    """The editable block at the top of every action button: a look (scene or color, set in Hue) and an
    effect on top (applied by SAMMI, because the Hue app cannot put effects or pulses into a scene)."""
    return [
        comment("SETTINGS - edit the values below, nothing else needs to change.\n"
                f"look: {LOOKS}\n"
                "lookValue, depending on look:\n"
                "  scene = the slot number filled by 'Hue: Link Scenes' (1-4)\n"
                "  color = " + ", ".join(n for n, _, _ in COLORS) + ", or x,y such as 0.6915,0.3083\n"
                "  white = warm, neutral, cool, or a number from 153 (cool) to 500 (warm)\n"
                "  off = empty for the Hue 3 target, or a scene slot to turn off that scene's room\n"
                "  on / none = leave empty (none keeps the current look and only applies the effect)\n"
                "brightness: 1-100 (color, white, on)\n"
                f"effect: {EFFECT_CHOICES}\n"
                "  candle, fire and the others run on every bulb of the scene (in each bulb's scene color) "
                "or of the Hue 3 target (in the look's color) until stop or another effect\n"
                "pulses: how many breathe pulses, about 2 seconds apart (effect breathe)\n"
                "speed: 0 (slow) to 1 (fast), for candle, fire and the others", 2),
        set_string("look", look),
        set_string("lookValue", look_value),
        set_string("brightness", str(brightness)),
        set_string("effect", effect),
        set_local("pulses", str(pulses)),
        set_string("speed", str(speed)),
        comment("END OF SETTINGS.", 2),
    ]


SETTING_NAMES = ["look", "lookValue", "brightness", "effect", "pulses", "speed"]
APPLY_ID = "hueApply"


def if_real_id(var, then, else_=()):
    """Runs `then` when `var` holds a Hue id (36 characters) rather than a placeholder (0, none, empty)."""
    return [str_len(f"{var}Len", f"/${var}$/"), if_(f"{var}Len", ">", "30", then, else_)]


EFFECT_NAMES = [e.strip() for e in EFFECTS.split(",")]


def resolve_color():
    named = [if_("lookValue", "==", f'"{n}"', [set_string("colorX", x), set_string("colorY", y), set_local("named", "1")])
             for n, x, y in COLORS]
    names = ", ".join(n for n, _, _ in COLORS)
    return [set_local("named", "0"), *named,
            if_("named", "==", "0", [
                str_pos("hasComma", "/$lookValue$/", ","),
                str_pos("hasDot", "/$lookValue$/", "."),
                if_("hasDot", "<=", "0", [set_local("hasComma", "0")]),       # x,y are decimals: 0.6915,0.3083
                if_("hasComma", ">", "0", [parse("xy", "[/$lookValue$/]"), set_string("colorX", "/$xy[0]$/"), set_string("colorY", "/$xy[1]$/")],
                    [alert(f"Hue: unknown color '/$lookValue$/'. Use {names}, or x,y such as 0.6915,0.3083."),
                     set_local("lookOk", "0")]),
            ])]


def resolve_white():
    named = [if_("lookValue", "==", f'"{n}"', [set_string("whiteMirek", m), set_local("named", "1")]) for n, m in WHITES]
    return [set_local("named", "0"), *named, if_("named", "==", "0", [set_string("whiteMirek", "/$lookValue$/")])]


def do_look():
    """Applies `look` to the Hue 3 target; a scene acts on its own room or zone."""
    return [
        set_string("resp", ""),
        set_local("known", "0"),
        set_local("lookOk", "1"),
        set_local("groupSent", "0"),
        if_("look", "==", '"scene"', [
            set_local("known", "1"),
            ini_load("scene_/$lookValue$/", "hueSceneId"),
            *if_real_id("hueSceneId", [*send(RECALL), set_local("groupSent", "1")], [
                alert("Hue: no scene linked for slot /$lookValue$/. Run 'Hue: Link Scenes' first."),
                set_local("lookOk", "0"),
            ]),
        ]),
        if_("look", "==", '"color"', [set_local("known", "1"), *resolve_color(), *send(put_light_vars(COLOR_BODY)), set_local("groupSent", "1")]),
        if_("look", "==", '"white"', [set_local("known", "1"), *resolve_white(), *send(put_light_vars(WHITE_BODY)), set_local("groupSent", "1")]),
        if_("look", "==", '"on"', [set_local("known", "1"), *send(put_light_vars(ON_BODY)), set_local("groupSent", "1")]),
        if_("look", "==", '"off"', [
            set_local("known", "1"),
            str_len("lvLen", "/$lookValue$/"),
            if_("lvLen", ">", "0", [
                ini_load("scene_/$lookValue$/_light", "offLight"),
                *if_real_id("offLight", [set_string("hueLightType", "grouped_light"), set_string("hueLightId", "/$offLight$/")]),
            ]),
            *send(OFF),
            set_local("groupSent", "1"),
        ]),
        if_("look", "==", '"none"', [set_local("known", "1")]),
        if_("known", "==", "0", [alert(f"Hue: unknown look '/$look$/'. Use one of: {LOOKS}."), set_local("lookOk", "0")]),
        str_pos("errPos", "/$resp$/", '"description"'),
        if_("errPos", ">", "0", [alert("Hue rejected the look: /$resp$/")]),
        if_("look", "!=", '"none"', [
            if_("lookOk", "==", "1", [
                str_len("respLen", "/$resp$/"),
                if_("respLen", "==", "0", [alert("Hue: no reply from the bridge (bridge off or wrong IP). Run Hue 1: Discover, then Hue 4: Test.")]),
            ]),
        ]),
    ]


def bulbs_of_scene():
    """fxIds: the scene's bulbs (each action's target is a light id, always present)."""
    return [
        *send(f'{CURL} {SCENE_URL} -H "hue-application-key: /$hueKey$/"'),
        set_local("nAct", "0"),
        str_pos("hasActs", "/$resp$/", '"actions"'),
        if_("hasActs", ">", "0", [parse("sc", "/$resp$/"), arr_size("sc.data[0].actions", "nAct")],
            [alert("Hue: could not read scene slot /$lookValue$/ (/$resp$/). Run 'Hue: Link Scenes' again.")]),
        set_local("i", "0"),
        repeat("nAct", [
            set_string("ids", '/$sep$/"/$sc.data[0].actions[i].target.rid$/"', rel=True),
            set_string("sep", ","),
            set_local("i", "1", op="+="),
        ]),
    ]


def bulbs_of_target():
    """fxIds: the Hue 3 target's bulbs. A zone lists its bulbs; a room lists devices, so match each
    bulb's owner device against the room's children. The group id is tried as a room, then as a zone,
    and every array is read only after the reply proves it is there (a missing path crashes SAMMI)."""
    add = lambda rid_expr: [set_string("ids", f'/$sep$/"{rid_expr}"', rel=True), set_string("sep", ",")]
    get = lambda kind: send(f'{CURL} "https:///$hueIp$//clip/v2/resource/{kind}//$hueGroupId$/" -H "hue-application-key: /$hueKey$/"')
    return [
        if_("hueLightType", "==", '"light"', add("/$hueLightId$/"), [
            ini_load("group_id", "hueGroupId"),
            *get("room"),
            str_pos("hasKids", "/$resp$/", '"children"'),
            if_("hasKids", "<=", "0", [*get("zone"), str_pos("hasKids", "/$resp$/", '"children"')]),
            if_("hasKids", "<=", "0", [
                alert("Hue: could not read the Hue 3 target's room or zone (/$resp$/). Run Hue 3: Pick Target again."),
            ], [
                parse("grp", "/$resp$/"),
                arr_size("grp.data[0].children", "nCh"),
                str_pos("isRoom", "/$resp$/", '"rtype":"device"'),
                if_("isRoom", "<=", "0", [
                    set_local("i", "0"),
                    repeat("nCh", [*add("/$grp.data[0].children[i].rid$/"), set_local("i", "1", op="+=")]),
                ], [
                    *send(f'{CURL} "https:///$hueIp$//clip/v2/resource/light" -H "hue-application-key: /$hueKey$/"'),
                    str_pos("hasData", "/$resp$/", '"owner"'),
                    if_("hasData", ">", "0", [
                        parse("allLights", "/$resp$/"),
                        arr_size("allLights.data", "nAll"),
                        set_local("i", "0"),
                        repeat("nAll", [
                            set_local("j", "0"),
                            repeat("nCh", [
                                str_pos("same", "/$allLights.data[i].owner.rid$/", "/$grp.data[0].children[j].rid$/"),
                                if_("same", ">", "0", add("/$allLights.data[i].id$/")),
                                set_local("j", "1", op="+="),
                            ]),
                            set_local("i", "1", op="+="),
                        ]),
                    ]),
                ]),
            ]),
        ]),
    ]


FX_COLOR = {"on": {"on": True}, "effects_v2": {"action": {"effect": "/$effect$/", "parameters": {
    "speed": "@speed@", "color": {"xy": {"x": "@fx@", "y": "@fy@"}}}}}}
FX_PLAIN = {"on": {"on": True}, "effects_v2": {"action": {"effect": "/$effect$/", "parameters": {"speed": "@speed@"}}}}
FX_V1 = {"on": {"on": True}, "effects": {"effect": "/$effect$/"}}


def do_effect():
    """Applies `effect` after the look. breathe is an alert on the scene's room or the target; the
    others are set bulb by bulb, because Hue has effects on bulbs only. Bulbs that cannot run effects
    (plugs, white-only bulbs) are skipped quietly; the button alerts only when no bulb took the effect."""
    per_bulb = [
        set_string("ids", ""), set_string("sep", ""),
        if_("look", "==", '"scene"', bulbs_of_scene(), bulbs_of_target()),
        parse("fxIds", "[/$ids$/]"),
        arr_size("fxIds", "nFx"),
        set_string("hueLightType", "light"),
        set_local("fxOk", "0"),
        set_string("fxLastErr", ""),
        set_local("i", "0"),
        repeat("nFx", [
            if_("i", ">", "0", [wait_ms("150")]),                    # keep a room's bulbs under ~10 commands/s
            set_string("hueLightId", "/$fxIds[i]$/"),
            # Ask the bulb itself; read a field only after its reply text shows it is there.
            *send(f'{CURL} {LIGHT_URL} -H "hue-application-key: /$hueKey$/"'),
            set_string("bulb", "/$resp$/"),
            str_pos("canFx", "/$bulb$/", '"effects"'),
            set_local("skip", "0"),
            if_("canFx", "<=", "0", [set_local("skip", "1")]),                 # plug or white-only bulb
            if_("look", "==", '"scene"', [
                str_pos("isOff", "/$bulb$/", '"on":{"on":false}'),
                if_("isOff", ">", "0", [set_local("skip", "1")]),             # the scene leaves it off
            ]),
            set_string("fx", ""), set_string("fy", ""),
            if_("look", "==", '"color"', [set_string("fx", "/$colorX$/"), set_string("fy", "/$colorY$/")]),
            if_("look", "==", '"scene"', [
                str_pos("hasXy", "/$bulb$/", '"xy"'),
                if_("hasXy", ">", "0", [parse("bulbObj", "/$bulb$/"), set_string("fx", "/$bulbObj.data[0].color.xy.x$/"),
                                        set_string("fy", "/$bulbObj.data[0].color.xy.y$/")]),
            ]),
            if_("skip", "==", "1", [set_string("resp", "")], [
            if_("effect", "==", '"stop"', send(put_light({"effects": {"effect": "no_effect"}})), [
                str_len("fxLen", "/$fx$/"),
                if_("fxLen", ">", "0", send(put_light_vars(FX_COLOR)), send(put_light_vars(FX_PLAIN))),
                str_pos("errPos", "/$resp$/", '"description"'),
                if_("errPos", ">", "0", send(put_light_vars(FX_V1))),   # older bulb firmware: no speed or color
            ]),
            str_pos("errPos", "/$resp$/", '"description"'),
            if_("errPos", ">", "0", [set_string("fxLastErr", "/$resp$/")], [set_local("fxOk", "1", op="+=")]),
            ]),
            set_local("i", "1", op="+="),
        ]),
        if_("effect", "!=", '"stop"', [
            if_("nFx", "==", "0", [alert("Hue: found no bulbs for the effect. Run Hue 3: Pick Target again, then try once more.")], [
                if_("fxOk", "==", "0", [alert("Hue: no bulb took the effect '/$effect$/' (none of them can run effects, or the bridge refused: /$fxLastErr$/).")]),
            ]),
        ]),
    ]
    known = [if_("effect", "==", f'"{e}"', [set_local("fxKnown", "1")]) for e in ["none", "breathe", "stop", *EFFECT_NAMES]]
    return [
        set_local("fxKnown", "0"),
        *known,
        if_("fxKnown", "==", "0", [alert(f"Hue: unknown effect '/$effect$/'. Use one of: {EFFECT_CHOICES}.")]),
        if_("look", "==", '"off"', [
            if_("effect", "!=", '"none"', [
                if_("effect", "!=", '"stop"', [alert("Hue: look off with an effect would turn the lights back on, so the effect was skipped."),
                                               set_local("fxKnown", "0")]),
            ]),
        ]),
        if_("lookOk", "==", "1", [
            if_("fxKnown", "==", "1", [
                if_("effect", "!=", '"none"', [
                    *LOAD_ALL(),
                    if_("effect", "==", '"breathe"', [
                        if_("look", "==", '"scene"', [
                            ini_load("scene_/$lookValue$/_light", "offLight"),
                            *if_real_id("offLight", [set_string("hueLightType", "grouped_light"), set_string("hueLightId", "/$offLight$/")]),
                        ]),
                        if_("groupSent", "==", "1", [wait_ms("1000")]),   # the look just went to this group: 1 command/s
                        if_("pulses", "<", "1", [set_local("pulses", "1")]),
                        set_local("bt", "0"),
                        repeat("pulses", [
                            if_("bt", ">", "0", [wait_ms("2000")]),
                            *send(BREATHE),
                            set_local("bt", "1", op="+="),
                        ]),
                    ], per_bulb),
                ]),
            ]),
        ]),
    ]


def show_list(title):
    """SAMMI's input popup cannot scroll, so a long list is unusable there. Write it to a text
    file in the SAMMI folder and open it in Notepad, which scrolls; the popup only asks for the number."""
    return [
        file_delete(LIST_FILE),
        file_append(LIST_FILE, f"{title}\n\n/$list$/"),
        shell(f'start "" notepad.exe "{LIST_FILE}"'),
    ]


def scenes_grouped_by(groups, count_var, label):
    """Append to `list` one block per room/zone: a heading, then every scene whose group.rid is that
    room/zone's id (and whose name matches the optional filter). Headings with no scenes are skipped.
    The room/zone chosen in Hue 3: Pick Target gets a marker, because a scene only ever changes the
    lights of its own room/zone."""
    return [
        set_local("r", "0"),
        repeat(count_var, [
            set_string("sub", ""),
            set_local("subHits", "0"),
            set_local("i", "0"),
            repeat("n", [
                set_local("hit", "1"),
                if_("filterLen", ">", "0", [
                    str_pos("hit", "/$scenes.data[i].metadata.name$/", "/$filter$/", ci=True),
                ]),
                if_("hit", ">", "0", [
                    str_pos("same", "/$scenes.data[i].group.rid$/", f"/${groups}.data[r].id$/"),
                    if_("same", ">", "0", [
                        set_string("sub", "   /$i$/ = /$scenes.data[i].metadata.name$/\n", rel=True),
                        set_local("subHits", "1", op="+="),
                        set_local("shown", "1", op="+="),
                    ]),
                ]),
                set_local("i", "1", op="+="),
            ]),
            if_("subHits", ">", "0", [
                set_string("heading", f"== /${groups}.data[r].metadata.name$/ ({label}) =="),
                str_pos("isTarget", "/$hueGroupId$/", f"/${groups}.data[r].id$/"),
                if_("isTarget", ">", "0", [
                    set_string("heading", "   <-- the target picked in Hue 3; scenes here change the lights you expect", rel=True),
                ]),
                set_string("list", "/$heading$/\n/$sub$/\n", rel=True),
            ]),
            set_local("r", "1", op="+="),
        ]),
    ]


def scene_group_name(num_var, save_var, light_var):
    """Set `save_var` to "Room name (room)" / "Zone name (zone)" for the scene at scenes.data[num_var], and
    `light_var` to that room/zone's grouped_light id (what a sequence turns off), or 0 if not found."""
    out = [set_string(save_var, "unknown room"), set_string(light_var, "0")]
    for groups, label in (("rooms", "room"), ("zones", "zone")):
        out += [
            set_local("r", "0"),
            repeat("nR" if groups == "rooms" else "nZ", [
                str_pos("same", f"/$scenes.data[{num_var}].group.rid$/", f"/${groups}.data[r].id$/"),
                if_("same", ">", "0", [
                    set_string(save_var, f"/${groups}.data[r].metadata.name$/ ({label})"),
                    set_string(light_var, f"/${groups}.data[r].services[0].rid$/"),
                ]),
                set_local("r", "1", op="+="),
            ]),
        ]
    return out


LOAD_ALL = lambda: [ini_load("ip", "hueIp"), ini_load("key", "hueKey"),
                    ini_load("light", "hueLightId"), ini_load("light_type", "hueLightType")]
SCENE_SLOTS = [(str(i), f"Scene {i}") for i in range(1, 5)]   # 'Hue: Link Scenes' fills these; buttons and sequences refer to them by number


def discovery(silent):
    ok_then = [
        parse("disc", "/$resp$/"),
        ini_save("ip", "/$disc[0].internalipaddress$/"),
        alert("Hue bridge at /$disc[0].internalipaddress$/ (saved to the ini file)"),
    ]
    if silent:
        ok_else = [alert("Hue: automatic bridge discovery failed, keeping the saved IP.")]
    else:
        ok_else = [popup("Could not find the bridge automatically.\n\n"
                         "In the Hue app on a phone: Settings > My Hue System > tap the bridge > read the IP address.\n"
                         "Then click 'Hue Config: Set IP' and type it in.\n\n"
                         "Raw response: /$resp$/")]
    return [
        delete_var("resp"),
        shell(f"{CURL} https://discovery.meethue.com", "resp"),
        wait_exists("resp", 10000),
        str_pos("okPos", "/$resp$/", "internalipaddress"),
        if_("okPos", ">", "0", ok_then, ok_else),
    ]


# ----------------------------------------------------------------------------
# buttons
# ----------------------------------------------------------------------------
def button(bid, text, x, y, color, commands, triggers=(), w=0.25, h=0.125, queueable=False, persistent=False, group=""):
    cmds = number(flatten(commands))
    trg = [dict(t, button_id=bid) for t in triggers]
    functions = (1 if cmds else 0) + (16 if trg else 0) + (64 if persistent else 0) + (128 if queueable else 0)
    return {
        "color": color, "persistent": 1.0 if persistent else 0.0, "text": text,
        "release_duration": 0.0, "queueable": 1.0 if queueable else 0.0,
        "command_list": cmds, "press_type": 0.0, "x": x, "border": 2.0, "image": "",
        "triggers": trg, "group_id": group, "overlappable": 0.0, "init_variable": "",
        "deck": 0.0, "width": w, "button_id": bid, "button_duration": 0.0, "y": y,
        "switch_deck": "", "height": h, "release_list": [], "functions": float(functions),
        "stretch": 0.0, "is_transparent": 0.0,
    }


STARTUP_TRIGGER = {"trg": 10.0, "type": "SAMMI Startup", "group_id": ""}


def action_button(bid, text, x, color, *, look="none", look_value="", brightness=100, effect="none",
                  pulses=1, speed="0.5", y=0.5, reset_hook=True):
    """An action button: its settings, then a call to the shared 'hueApply' button, which reads these
    settings back (Get Button Variable needs this button's variables to persist) and does the work.
    The user attaches any SAMMI trigger (right-click > Edit Triggers)."""
    hook = [trigger_button("hueReset", 10000, disabled=True)] if reset_hook else []   # optional 10 s auto-reset
    return button(bid, text, x, y, color, [
        comment("ACTION BUTTON. Attach any trigger to it: right-click the button > Edit Triggers. "
                "It hands its settings to 'Hue: apply (shared)', which sets the look, then the effect. "
                "Do not turn off 'Persistent Variables' on this button: the shared button reads the settings from it.", 1),
        *action_settings(look, look_value, brightness, effect, pulses, speed),
        trigger_button(APPLY_ID, 0, queueable=True),
        *hook,
    ], persistent=True)


def apply_button():
    """The one implementation of look + effect. Started by Trigger Button from an action button; reads
    that button's settings, so queued runs from a burst each use their own caller's settings."""
    return button(APPLY_ID, "Hue: apply\n(shared)", 0.75, 0.25, DARK, [
        comment("SHARED. Do not attach triggers or edit this button. Every action button calls it with Trigger Button; "
                "it reads the caller's settings, sets the look, then the effect, then holds 1 s so bursts stay under "
                "Hue's rate limit (1 command/s for rooms, zones and scenes). Calls that arrive meanwhile queue up.", 2),
        trigger_pull("origin", "button_id"),
        str_len("originLen", "/$origin$/"),
        if_("originLen", "==", "0", [set_string("origin", APPLY_ID)]),
        if_("origin", "==", f'"{APPLY_ID}"', [
            alert("Hue: 'Hue: apply (shared)' runs when an action button calls it. Press an action button instead."),
        ], [
            *[get_button_var("/$origin$/", v, v) for v in SETTING_NAMES],
            set_string("fadeMs", FADE_MS),
            *LOAD_ALL(),
            *do_look(),
            *do_effect(),
            overtime(1000),
        ]),
    ], queueable=True)


def try_action():
    """Lists what the Hue 3 target supports (asked from the bridge, so nothing is assumed) plus fixed
    colors, whites, on and off; sends the one picked and says how to put it on an action button."""
    fixed = ([(f"color: {n}", {"on": {"on": True}, "dimming": {"brightness": 100}, "color": {"xy": {"x": float(x), "y": float(y)}}},
               f"look color, lookValue {n}") for n, x, y in COLORS]
             + [(f"white: {n}", {"on": {"on": True}, "dimming": {"brightness": 100}, "color_temperature": {"mirek": int(m)}},
                 f"look white, lookValue {n}") for n, m in WHITES]
             + [("turn on", {"on": {"on": True}}, "look on"),
                ("turn off", {"on": {"on": False}}, "look off")])
    n_fixed = len(fixed)
    listing_lines = "".join(f"{i} = {label}\n" for i, (label, _, _) in enumerate(fixed))
    sections = [  # (marker in the reply, array path, label, count var)
        ('"alert"', "t.data[0].alert.action_values", "alert", "nA"),
        ('"signaling"', "t.data[0].signaling.signal_values", "signal", "nS"),
        ('"effects"', "t.data[0].effects.effect_values", "effect", "nE"),
        ('"timed_effects"', "t.data[0].timed_effects.effect_values", "timed effect", "nT"),
    ]
    build = []
    for marker, path, label, count in sections:
        build += [
            set_local(count, "0"),
            str_pos("has", "/$resp$/", marker),
            if_("has", ">", "0", [arr_size(path, count)]),
            set_local("i", "0"),
            repeat(count, [
                set_string("list", f"/$k$/ = {label}: /${path}[i]$/\n", rel=True),
                set_local("i", "1", op="+="),
                set_local("k", "1", op="+="),
            ]),
        ]
    fixed_ifs = [if_("pickNum", "==", str(i), [*send(put_light(body)), set_string("hint", hint)])
                 for i, (_, body, hint) in enumerate(fixed)]
    return [
        comment("Asks the bridge what the Hue 3 target supports, lists it in Notepad with a few fixed colors, "
                "and sends the one you pick. Effects exist on bulbs only; a room or zone lists alerts and signals.", 1),
        *LOAD_ALL(),
        *send(f'{CURL} {LIGHT_URL} -H "hue-application-key: /$hueKey$/"'),
        str_pos("okPos", "/$resp$/", '"data"'),
        if_("okPos", ">", "0", [
            parse("t", "/$resp$/"),
            set_string("list", listing_lines),
            set_local("k", str(n_fixed)),
            *build,
            *show_list("Actions for the Hue 3 target (colors and whites are fixed; the rest is what the bridge says this target supports). "
                       "Type the number into SAMMI."),
            wait_input("A Notepad window just opened listing the actions this target supports (file hue_scenes_list.txt).\n\n"
                       "Type the NUMBER of the action to try, then click OK.", "0", "pick"),
            str_to_num("pickNum", "pick"),
            set_string("hint", ""),
            *fixed_ifs,
            set_local("kind", "0"),
            set_local("b1", str(n_fixed)),
            set_local("b2", f"({n_fixed} + nA)"),
            set_local("b3", f"({n_fixed} + nA + nS)"),
            set_local("b4", f"({n_fixed} + nA + nS + nE)"),
            set_local("b5", f"({n_fixed} + nA + nS + nE + nT)"),
            if_("pickNum", ">=", "b1", [set_local("kind", "1"), set_local("idx", "(pickNum - b1)")]),
            if_("pickNum", ">=", "b2", [set_local("kind", "2"), set_local("idx", "(pickNum - b2)")]),
            if_("pickNum", ">=", "b3", [set_local("kind", "3"), set_local("idx", "(pickNum - b3)")]),
            if_("pickNum", ">=", "b4", [set_local("kind", "4"), set_local("idx", "(pickNum - b4)")]),
            if_("pickNum", ">=", "b5", [set_local("kind", "0"), alert("Hue: /$pick$/ is not on the list.")]),
            if_("kind", "==", "1", [
                set_string("val", "/$t.data[0].alert.action_values[idx]$/"),
                *send(put_light({"alert": {"action": "/$val$/"}})),
                set_string("hint", "effect breathe, pulses 1 (or more)"),
            ]),
            if_("kind", "==", "2", [
                set_string("signal", "/$t.data[0].signaling.signal_values[idx]$/"),
                set_string("signalMs", "8000"),
                set_string("colorX", "0.6915"), set_string("colorY", "0.3083"),
                set_string("colorX2", "0.1532"), set_string("colorY2", "0.0475"),
                *send_signal(),
                set_string("hint", "nothing - signals are only in Try Action; buttons offer breathe and the effects"),
            ]),
            if_("kind", "==", "3", [
                set_string("val", "/$t.data[0].effects.effect_values[idx]$/"),
                *send(put_light({"on": {"on": True}, "effects": {"effect": "/$val$/"}})),
                set_string("hint", "effect /$val$/ (with look none, a scene or a color; it runs until effect stop)"),
            ]),
            if_("kind", "==", "4", [
                set_string("val", "/$t.data[0].timed_effects.effect_values[idx]$/"),
                *send(put_light({"timed_effects": {"effect": "/$val$/", "duration": 60000}})),
                set_string("hint", "nothing - timed effects are only in Try Action"),
            ]),
            *check_reply("bridge off or wrong IP"),
            str_len("hintLen", "/$hint$/"),
            if_("hintLen", ">", "0", [
                alert("Sent. To put this on an action button, copy an Example button and set: /$hint$/"),
            ]),
        ], [
            popup("Could not read the target.\n\nBridge said: /$resp$/\n\n"
                  "Run Hue 3: Pick Target first. 'unauthorized user' = run Hue 2: Pair again."),
        ]),
    ]


SEQ_GROUP = "hueSeq"


def sequence_button(bid, text, x, y, color, *, scene1="1", effect1="none", seconds1="30",
                    scene2="2", effect2="none", seconds2="30", when_done="loop", max_minutes="0"):
    """Up to two linked scenes, each with its own effect and hold time, then loop, off or stay. Each step
    sets this button's look/effect settings and calls the shared apply button, like an action button."""
    def step(n):
        return [
            set_string("look", "scene"),
            set_string("lookValue", f"/$scene{n}$/"),
            set_string("effect", f"/$effect{n}$/"),
            trigger_button(APPLY_ID, 0, queueable=True),
            wait_ms(f"ms{n}"),
            set_local("elapsed", f"ms{n}", op="+="),
        ]

    def lights_off():
        out = []
        for n in (1, 2):
            out.append(if_(f"scene{n}Len", ">", "0", [
                set_string("look", "off"), set_string("lookValue", f"/$scene{n}$/"), set_string("effect", "none"),
                trigger_button(APPLY_ID, 0, queueable=True),
                wait_ms("1200"),        # let the shared button read these settings before they change
            ]))
        return out

    return button(bid, text, x, y, color, [
        comment("SCENE SEQUENCE. Attach any trigger (right-click > Edit Triggers). Shows scene 1 with effect 1 for "
                "seconds1, then scene 2 with effect 2 for seconds2, then does whenDone. 'Hue: Stop sequence' stops it.", 1),
        comment("SETTINGS - edit the values below.\n"
                "scene1 / scene2: a scene slot linked with 'Hue: Link Scenes' (1-4). Leave scene2 empty for one scene\n"
                f"effect1 / effect2: {EFFECT_CHOICES}\n"
                "seconds1 / seconds2: how long to hold each scene (1 or more)\n"
                "whenDone: loop = start again (until stopped or maxMinutes), off = turn the scenes' rooms off, stay = leave as is\n"
                "maxMinutes: with loop, turn off and stop after this many minutes; 0 = until stopped", 2),
        set_string("scene1", scene1),
        set_string("effect1", effect1),
        set_local("seconds1", seconds1),
        set_string("scene2", scene2),
        set_string("effect2", effect2),
        set_local("seconds2", seconds2),
        set_string("whenDone", when_done),
        set_local("maxMinutes", max_minutes),
        comment("END OF SETTINGS.", 2),
        stop_button(SEQ_GROUP, ongoing=True, queued=True, include_self=False),
        set_string("brightness", "100"),
        set_local("pulses", "1"),
        set_string("speed", "0.5"),
        set_local("ms1", "(seconds1 * 1000)"),
        set_local("ms2", "(seconds2 * 1000)"),
        set_local("maxMs", "(maxMinutes * 60000)"),
        str_len("scene1Len", "/$scene1$/"),
        str_len("scene2Len", "/$scene2$/"),
        set_local("elapsed", "0"),
        set_local("done", "0"),
        if_("scene1Len", "==", "0", [alert("Hue sequence: set scene1 to a linked slot (1-4)."), set_local("done", "1")]),
        if_("ms1", "<", "1000", [alert("Hue sequence: seconds1 must be 1 or more."), set_local("done", "1")]),
        if_("scene2Len", ">", "0", [
            if_("ms2", "<", "1000", [alert("Hue sequence: seconds2 must be 1 or more."), set_local("done", "1")]),
        ]),
        repeat("100000", [
            break_if("done", "==", "1"),
            *step(1),
            if_("scene2Len", ">", "0", step(2)),
            if_("whenDone", "==", '"loop"', [
                if_("maxMs", ">", "0", [if_("elapsed", ">=", "maxMs", [*lights_off(), set_local("done", "1")])]),
            ], [
                if_("whenDone", "==", '"off"', lights_off()),
                set_local("done", "1"),
            ]),
        ]),
    ], group=SEQ_GROUP, persistent=True)


BUTTONS = [
    # --- row 0: setup, in order --------------------------------------------
    button("hueDiscover", "Hue 1:\nDiscover", 0.0, 0.0, GRAY, [
        comment("Finds the Hue Bridge on the LAN through Hue's discovery service and saves its IP to the ini file in the SAMMI folder.", 1),
        *discovery(silent=False),
    ]),
    button("huePair", "Hue 2:\nPair", 0.25, 0.0, GRAY, [
        comment("Mints an app key. The bridge only answers while its link button was pressed in the last 30 s.", 1),
        ini_load("ip", "hueIp"),
        popup("Press the big round button on top of the Hue Bridge, then click OK within 30 seconds.", pause=True),
        delete_var("resp"),
        shell(f'{CURL} -X POST "https:///$hueIp$//api" -H "Content-Type: application/json" '
              f'-d "{cmd_json({"devicetype": "sammi#hue_scenes", "generateclientkey": True})}"', "resp"),
        wait_exists("resp", 10000),
        str_pos("okPos", "/$resp$/", "success"),
        if_("okPos", ">", "0", [
            parse("pair", "/$resp$/"),
            ini_save("key", "/$pair[0].success.username$/"),
            alert("Paired. App key saved to the ini file."),
        ], [
            popup("Pairing failed.\n\nBridge said: /$resp$/\n\n"
                  "Usual cause: 'link button not pressed'. Press the bridge button again, "
                  "you click Hue 2: Pair straight away.\n"
                  "Empty response: wrong IP (run Hue 1: Discover or Hue Config: Set IP)."),
        ]),
    ]),
    button("huePickLight", "Hue 3:\nPick Target", 0.5, 0.0, GRAY, [
        comment("Lists every bulb, room and zone on the bridge, asks which number to control, saves its id and type. "
                "A room or zone is driven through its 'grouped_light', so every bulb in it reacts.", 1),
        ini_load("ip", "hueIp"),
        ini_load("key", "hueKey"),
        delete_var("resp"),
        shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/light" -H "hue-application-key: /$hueKey$/"', "resp"),
        wait_exists("resp", 10000),
        str_pos("okPos", "/$resp$/", '"data"'),
        if_("okPos", ">", "0", [
            parse("lights", "/$resp$/"),
            delete_var("resp2"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/room" -H "hue-application-key: /$hueKey$/"', "resp2"),
            wait_exists("resp2", 10000),
            set_local("nR", "0"),
            str_pos("okrooms", "/$resp2$/", '"data"'),
            if_("okrooms", ">", "0", [parse("rooms", "/$resp2$/"), arr_size("rooms.data", "nR")]),
            delete_var("resp3"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/zone" -H "hue-application-key: /$hueKey$/"', "resp3"),
            wait_exists("resp3", 10000),
            set_local("nZ", "0"),
            str_pos("okzones", "/$resp3$/", '"data"'),
            if_("okzones", ">", "0", [parse("zones", "/$resp3$/"), arr_size("zones.data", "nZ")]),
            arr_size("lights.data", "nL"),
            set_local("k", "0"),
            set_string("list", ""),
            set_local("i", "0"),
            repeat("nL", [
                set_string("list", "/$k$/ = /$lights.data[i].metadata.name$/   (bulb)\n", rel=True),
                set_local("i", "1", op="+="),
                set_local("k", "1", op="+="),
            ]),
            set_local("i", "0"),
            repeat("nR", [
                set_string("list", "/$k$/ = /$rooms.data[i].metadata.name$/   (room, every bulb in it)\n", rel=True),
                set_local("i", "1", op="+="),
                set_local("k", "1", op="+="),
            ]),
            set_local("i", "0"),
            repeat("nZ", [
                set_string("list", "/$k$/ = /$zones.data[i].metadata.name$/   (zone, every bulb in it)\n", rel=True),
                set_local("i", "1", op="+="),
                set_local("k", "1", op="+="),
            ]),
            *show_list("Bulbs, rooms and zones on this bridge. Type the number of the one the action buttons should control into SAMMI."),
            wait_input("A Notepad window just opened listing every bulb, room and zone (file hue_scenes_list.txt in the SAMMI folder).\n\n"
                       "Type the NUMBER the action buttons should control, then click OK.", "0", "pick"),
            str_to_num("pickNum", "pick"),
            set_local("kind", "9"),                       # 9 = not on the list; also what a non-number stays
            set_local("idx", "pickNum"),
            if_("pickNum", ">=", "0", [set_local("kind", "0")]),
            if_("pickNum", ">=", "nL", [set_local("kind", "1"), set_local("idx", "(pickNum - nL)")]),
            if_("pickNum", ">=", "(nL + nR)", [set_local("kind", "2"), set_local("idx", "(pickNum - nL - nR)")]),
            if_("pickNum", ">=", "(nL + nR + nZ)", [set_local("kind", "9")]),
            if_("kind", "==", "9", [alert("Hue: '/$pick$/' is not on the list. Nothing was changed; run Hue 3 again.")]),
            if_("kind", "==", "0", [
                ini_save("light", "/$lights.data[idx].id$/"),
                ini_save("light_type", "light"),
                ini_save("light_name", "/$lights.data[idx].metadata.name$/ (bulb)"),
                ini_save("group_id", "none"),
                ini_save("group_kind", "none"),
            ]),
            if_("kind", "==", "1", [
                ini_save("light", "/$rooms.data[idx].services[0].rid$/"),
                ini_save("light_type", "grouped_light"),
                ini_save("light_name", "/$rooms.data[idx].metadata.name$/ (room)"),
                ini_save("group_id", "/$rooms.data[idx].id$/"),
                ini_save("group_kind", "room"),
            ]),
            if_("kind", "==", "2", [
                ini_save("light", "/$zones.data[idx].services[0].rid$/"),
                ini_save("light_type", "grouped_light"),
                ini_save("light_name", "/$zones.data[idx].metadata.name$/ (zone)"),
                ini_save("group_id", "/$zones.data[idx].id$/"),
                ini_save("group_kind", "zone"),
            ]),
            if_("kind", "!=", "9", [
                ini_load("light_name", "hueLightName"),
                alert("Action buttons will control '/$hueLightName$/' (saved to the ini file)"),
            ]),
        ], [
            popup("Could not list the lights.\n\nBridge said: /$resp$/\n\n"
                  "'unauthorized user' = run Hue 2: Pair again. Empty = wrong IP or bridge off."),
        ]),
    ]),
    button("hueTest", "Hue 4:\nTest", 0.75, 0.0, GRAY, [
        comment("Sends a 'breathe' alert so the chosen bulb, room or zone pulses once.", 1),
        *LOAD_ALL(),
        delete_var("resp"),
        shell(put_light({"alert": {"action": "breathe"}}), "resp"),
        wait_exists("resp", 10000),
        alert("Test sent, the light(s) should pulse once. Bridge said: /$resp$/"),
    ]),
    button("hueProbe", "Hue 5: Probe\n(optional)", 0.0, 0.125, DARK, [
        comment("Diagnostic only. Tries SAMMI's own HTTP Request against the bridge's HTTPS. The deck does not depend on this; "
                "it exists to settle the Phase 0 TLS question on real hardware.", 2),
        ini_load("ip", "hueIp"),
        delete_var("probe"),
        http("https:///$hueIp$//api/0/config", "GET", "", "", "probe"),
        wait_exists("probe", 6000),
        popup("Native HTTPS probe.\n\nIf bridge config JSON appears below, SAMMI's HTTP Request accepts the bridge "
              "certificate on this PC. If you got a red HTTP error instead, the curl-based commands this deck already "
              "uses are the right choice.\n\n/$probe$/", pause=False),
    ]),

    # --- row 1: config / status ---------------------------------------------
    button("hueConfig", "Hue Config:\nSet IP", 0.25, 0.125, TEAL, [
        comment("Manual fallback when discovery fails. Writes the bridge IP to the ini file.", 1),
        ini_load("ip", "hueIp"),
        wait_input("Hue Bridge IP address (Hue app > Settings > My Hue System > bridge):", "/$hueIp$/", "newIp"),
        ini_save("ip", "/$newIp$/"),
        alert("Bridge IP saved: /$newIp$/"),
    ]),
    button("hueShow", "Hue: Show\nSettings", 0.5, 0.125, TEAL, [
        *LOAD_ALL(),
        ini_load("light_name", "hueLightName"),
        *[ini_load(f"scene_{slot}_name", f"scene_{slot}") for slot, _ in SCENE_SLOTS],
        popup(f"Hue Scenes settings (file: {INI} in the SAMMI folder)\n\n"
              "Bridge IP: /$hueIp$/\nApp key: /$hueKey$/\n"
              "Target: /$hueLightName$/\nTarget id: /$hueLightId$/ (/$hueLightType$/)\n\n"
              "Linked scenes (used by action scene, value = slot):\n"
              + "".join(f"  {label}: /$scene_{slot}$/\n" for slot, label in SCENE_SLOTS)
              + "\nA value of 0 means it has not been set yet.", pause=False),
    ]),
    button("hueScenes", "Hue: Link\nScenes", 0.25, 0.25, TEAL, [
        comment("The user creates a scene in the Hue app (any colors, any number of bulbs in the room or zone). "
                "This button lists the bridge's scenes and links each button to one of them. Buttons with action scene "
                "recall the linked scene, so changing a color later is just editing the scene in the Hue app.", 1),
        ini_load("ip", "hueIp"),
        ini_load("key", "hueKey"),
        delete_var("resp"),
        shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/scene" -H "hue-application-key: /$hueKey$/"', "resp"),
        wait_exists("resp", 10000),
        str_pos("okPos", "/$resp$/", '"data"'),
        if_("okPos", ">", "0", [
            parse("scenes", "/$resp$/"),
            arr_size("scenes.data", "n"),
            delete_var("resp2"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/room" -H "hue-application-key: /$hueKey$/"', "resp2"),
            wait_exists("resp2", 10000),
            set_local("nR", "0"),
            str_pos("okrooms", "/$resp2$/", '"data"'),
            if_("okrooms", ">", "0", [parse("rooms", "/$resp2$/"), arr_size("rooms.data", "nR")]),
            delete_var("resp3"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/zone" -H "hue-application-key: /$hueKey$/"', "resp3"),
            wait_exists("resp3", 10000),
            set_local("nZ", "0"),
            str_pos("okzones", "/$resp3$/", '"data"'),
            if_("okzones", ">", "0", [parse("zones", "/$resp3$/"), arr_size("zones.data", "nZ")]),
            ini_load("group_id", "hueGroupId"),
            wait_input("Found /$n$/ scenes on this bridge.\n\n"
                       "Type part of a scene name to narrow the list (capitals do not matter), "
                       "or leave this empty to list every scene, then click OK.", "", "filter"),
            str_len("filterLen", "/$filter$/"),
            set_local("shown", "0"),
            set_string("list", ""),
            *scenes_grouped_by("rooms", "nR", "room"),
            *scenes_grouped_by("zones", "nZ", "zone"),
            *show_list("Scenes on this bridge, grouped by room / zone (filtered by '/$filter$/' if you typed one). Type the number of the scene to link into SAMMI."),
            *[c for slot, label in SCENE_SLOTS for c in [
                wait_input(f"A Notepad window just opened listing /$shown$/ scene(s), grouped by room and zone (file hue_scenes_list.txt in the SAMMI folder). "
                           "A scene changes the lights of ITS room/zone, so pick one from the group marked as your target.\n\n"
                           f"Which scene should **{label}** recall? Type its NUMBER, or -1 to leave this one unchanged.", "-1", f"pick_{slot}"),
                str_to_num(f"num{slot}", f"pick_{slot}"),
                if_(f"num{slot}", ">=", "n", [alert(f"Hue: /$pick_{slot}$/ is not on the list; {label} was left unchanged."),
                                               set_local(f"num{slot}", "-1")]),
                if_(f"num{slot}", ">=", "0", [
                    *scene_group_name(f"num{slot}", "groupName", "groupLight"),
                    ini_save(f"scene_{slot}", f"/$scenes.data[num{slot}].id$/"),
                    ini_save(f"scene_{slot}_light", "/$groupLight$/"),
                    ini_save(f"scene_{slot}_name", f"/$scenes.data[num{slot}].metadata.name$/ in /$groupName$/"),
                    alert(f"{label} -> scene '/$scenes.data[num{slot}].metadata.name$/' in /$groupName$/. "
                          "Recalling it changes every light in that room/zone, whatever Hue 3 picked."),
                ]),
            ]],
            alert("Scene links saved. Check them with Hue: Show Settings, then run 'Example: Hue scene' or 'Example: scene sequence'."),
        ], [
            popup("Could not list the scenes.\n\nBridge said: /$resp$/\n\n"
                  "'unauthorized user' = run Hue 2: Pair again. Empty = wrong IP or bridge off."),
        ]),
    ]),
    button("hueTryAction", "Hue: Try\nAction", 0.5, 0.25, TEAL, try_action()),
    apply_button(),
    button("hueStartup", "Hue: Auto\nrediscover", 0.0, 0.25, DARK, [
        comment("Runs by itself when SAMMI starts (SAMMI Startup trigger). Waits 15 s for the network, then refreshes the "
                "bridge IP in case the router handed out a new one. Safe to leave alone.", 2),
        wait_ms(15000),
        *discovery(silent=True),
    ], triggers=[STARTUP_TRIGGER]),
    button("hueHelp", "Hue Scenes:\nhow it works", 0.75, 0.125, DARK, [
        popup("Hue Scenes\n\n"
              "Setup once: Hue 1 Discover > Hue 2 Pair (press bridge button) > Hue 3 Pick Target (a bulb, a room or a zone) "
              "> Hue 4 Test > Hue: Link Scenes (pick the Hue-app scene the example scene button recalls).\n"
              "Settings live in the ini file in the SAMMI folder, so they survive restarts.\n\n"
              "Not sure what your lights can do? 'Hue: Try Action' lists what the Hue 3 target supports (colors, whites, "
              "breathe, signals, effects like candle or fire) and sends the one you pick.\n\n"
              "The bottom rows hold example buttons with no trigger attached. Attach any trigger to them "
              "(right-click > Edit Triggers), or copy them to make more. Each has a SETTINGS block at the top "
              "(right-click > Edit Commands): look (scene, color, white, on, off, none) with lookValue and brightness, "
              "then effect (none, breathe with pulses, candle, fire and the others with speed, or stop). "
              "The Hue app cannot put effects in a scene, so SAMMI applies them on top, bulb by bulb.\n"
              "A scene always acts on the lights of its own room/zone, not on the Hue 3 target. Link up to 4 scenes with Hue: Link Scenes.\n"
              "'Example: scene sequence' shows up to two linked scenes, each with its own effect and seconds, then loops, "
              "turns off or stays. Chain buttons with triggers for more. 'Hue: Stop sequence' stops it.\n\n"
              "Lights stopped reacting? Click Hue 1: Discover, then Hue 4: Test.", pause=False),
    ]),

    # --- rows 4-6: example buttons (no triggers shipped) ------------------------------------------------------
    action_button("hueScene1", "Example:\nHue scene", 0.0, TEAL, look="scene", look_value="1"),
    action_button("hueColorRed", "Example:\ncolor (red)", 0.25, RED, look="color", look_value="red"),
    action_button("hueReset", "Reset\n(optional)", 0.5, GRAY, look="white", look_value="neutral", brightness=60,
                  effect="stop", reset_hook=False),
    action_button("hueEffect", "Example:\neffect (candle)", 0.75, WARM, effect="candle"),
    action_button("hueSceneCandle", "Example:\nscene + candle", 0.0, TEAL, look="scene", look_value="1", effect="candle", y=0.625),
    action_button("hueColorFire", "Example:\norange + fire", 0.25, RED, look="color", look_value="orange", effect="fire", y=0.625),
    action_button("hueBreathe", "Example:\nbreathe x3", 0.5, TEAL, effect="breathe", pulses=3, y=0.625),
    action_button("hueOff", "Example:\nturn off", 0.75, DARK, look="off", effect="none", y=0.625),
    action_button("hueOn", "Example:\nturn on", 0.0, WARM, look="on", y=0.75),
    sequence_button("hueSequence", "Example:\nscene sequence", 0.25, 0.75, BLUE, effect2="candle"),
    button("hueStopSequence", "Hue: Stop\nsequence", 0.5, 0.75, GRAY, [
        comment("Stops every running sequence (button group 'hueSeq') and drops queued steps, including action buttons "
                "waiting in line from other triggers. The lights stay as they are; "
                "add an 'Example: turn off' trigger after it if you want them off.", 1),
        stop_button(SEQ_GROUP, ongoing=True, queued=True, include_self=False),
        stop_button(APPLY_ID, ongoing=False, queued=True, include_self=False),   # drop steps still waiting in line
        alert("Hue: sequence stopped."),
    ]),
]


# ----------------------------------------------------------------------------
# readable listing
# ----------------------------------------------------------------------------
NAMES = {83: "String Get Length", 255: "File: Append Text", 227: "File: Delete File", 6: "Comment", 142: "Alert Message", 141: "Popup Message", 78: "Delete Variable", 306: "Command Line",
         153: "Wait Until Variable Exists", 190: "Wait For Timeout", 168: "Parse Array/Object", 15: "Set Local Variable",
         20: "Set String Variable", 91: "String Position", 126: "INI: Save Text", 127: "INI: Load Text",
         214: "Wait For User Input", 79: "String to Number", 100: "Array Get Size", 137: "Overtime",
         169: "HTTP Request", 132: "Trigger Button", 7: "If", 9: "Repeat", 11: "Break", 133: "Stop Button/Group",
         66: "Trigger Pull Data", 162: "Get Button Variable"}


def describe(c):
    i = int(c["cmd"])
    b = lambda k: c.get(f"b{k}", "")
    one = lambda s: s.replace("\n", " / ")
    if i == 6:   return f"Comment: {one(b(0))}"
    if i == 142: return f"Alert: {one(b(0))}"
    if i == 141: return f"Popup{' (pauses button)' if c.get('v0') else ''}: {one(b(0))}"
    if i == 78:  return f"Delete Variable `{b(0)}`"
    if i == 306: return f"Command Line: `{b(0)}`" + (f" -> save as `{b(1)}`" if b(1) else "")
    if i == 153: return f"Wait Until Variable Exists `{b(0)}` (timeout {b(1)} ms)"
    if i == 190: return f"Wait For Timeout {b(0)} ms"
    if i == 168: return f"Parse Array/Object `{b(0)}` from `{b(1)}`"
    if i == 15:  return f"Set Local Variable `{b(0)}` {b(1)} `{b(2)}`"
    if i == 20:  return f"Set String Variable `{b(0)}` {'+=' if c.get('v0') else '='} `{one(b(1))}`"
    if i == 91:  return f"String Position `{b(0)}` = position of `{b(2)}` in `{b(1)}`{' (case insensitive)' if c.get('v0') else ''}"
    if i == 83:  return f"String Get Length `{b(0)}` of `{b(1)}`"
    if i == 255: return f"File: Append Text to `{b(0)}`: {one(b(1))}"
    if i == 227: return f"File: Delete File `{b(0)}`"
    if i == 126: return f"INI: Save Text {b(0)} [{b(1)}] {b(2)} = `{b(3)}`"
    if i == 127: return f"INI: Load Text {b(0)} [{b(1)}] {b(2)} -> `{b(3)}`"
    if i == 214: return f"Wait For User Input -> `{b(2)}` (default `{b(1)}`): {one(b(0))}"
    if i == 79:  return f"String to Number `{b(0)}` from `{b(1)}`"
    if i == 100: return f"Array Get Size `{b(0)}` -> `{b(1)}`"
    if i == 137: return f"Overtime {b(0)} ms"
    if i == 169: return f"HTTP Request {b(1)} {b(0)} -> `{b(4)}`"
    if i == 132: return f"Trigger Button `{b(0)}` after {b(1)} ms{' (queueable)' if c.get('v0') else ''}"
    if i == 7:   return f"If `{b(0)}` {b(1)} `{b(2)}`  (block {int(c['v0'])}, else {int(c.get('v1', 0))})"
    if i == 9:   return f"Repeat `{b(0)}` times  (block {int(c['v0'])})"
    if i == 11:  return f"Break if `{b(0)}` {b(1)} `{b(2)}`"
    if i == 66:  return f"Trigger Pull Data `{b(1)}` -> `{b(0)}`"
    if i == 162: return f"Get Button Variable `{b(1)}` from button `{b(0)}` -> `{b(2)}`"
    if i == 133: return f"Stop Button/Group `{b(0)}` (ongoing {bool(c.get('v0'))}, queued {bool(c.get('v1'))}, include self {bool(c.get('v2'))})"
    return f"cmd {i}"


def listing(buttons):
    lines = [f"# {DECK_NAME} deck, command listing", "",
             "Generated by `tools/build_deck.py`. Paste `deck/HueScenes.deck.json` into SAMMI with side menu > Paste Deck.",
             f"Settings file: `{INI}` in the SAMMI folder, section `[{SEC}]`, keys `ip`, `key`, `light`, `light_type`, `light_name`, `group_id`, `group_kind`, `scene_<slot>`, `scene_<slot>_name`, `scene_<slot>_light`.", ""]
    for bt in buttons:
        lines.append(f"## {bt['text'].replace(chr(10), ' ')}  (`{bt['button_id']}`)")
        for t in bt["triggers"]:
            if t["trg"] == 10.0:
                lines.append(f"- Trigger: SAMMI Trigger, {t['type']}")
            else:
                lines.append(f"- Trigger: type {int(t['trg'])}")
        if bt["queueable"]:
            lines.append("- Setting: Allow Queue on")
        lines.append("")
        # indentation from block sizes
        depth, stack = 0, []
        for c in bt["command_list"]:
            while stack and stack[-1] == 0:
                stack.pop()
            indent = "    " * len(stack)
            off = " (OFF)" if c.get("dis") else ""
            lines.append(f"{indent}{int(c['pos']) + 1}. {describe(c)}{off}")
            for k in range(len(stack)):      # block sizes count nested descendants, so every open block ticks down
                stack[k] -= 1
            if int(c["cmd"]) in (7, 9):
                n = int(c["v0"]) + int(c.get("v1", 0))
                stack.append(n)
        lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
README_START, README_END = "<!-- deck-json:start -->", "<!-- deck-json:end -->"


def inject_readme(deck_json):
    """Keep the copy-paste block in README.md in sync with the generated deck."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    a, b = text.find(README_START), text.find(README_END)
    if a < 0 or b < 0:
        return
    block = f"{README_START}\n```json\n{deck_json}\n```\n"
    readme.write_text(text[:a] + block + text[b:], encoding="utf-8")


def main():
    uid = time.strftime("%Y%m%d%H%M%S") + "000000000"
    deck_data = {
        "background_color": 4210752.0, "on": True, "grid_y": float(GRID_Y), "snap_grid": True,
        "lb_version": SAMMI_MIN_VERSION, "background_image": "", "sammi_version": SAMMI_MIN_VERSION,
        "encrypted": False, "adaptive_resizing": True, "unique_id": uid,
        "button_list": BUTTONS, "deck_name": DECK_NAME, "grid_x": float(GRID_X), "stretch": False,
    }
    wrapper = {"deck_data": json.dumps(deck_data), "unique_id": uid, "include_image": {},
               "sammi_version": SAMMI_MIN_VERSION}
    from audit_deck import audit                     # tools/audit_deck.py; nothing is written if it fails
    problems = audit(wrapper)
    if problems:
        raise SystemExit("deck audit failed, nothing written:\n" + "\n".join(problems))
    OUT_DIR.mkdir(exist_ok=True)
    deck_json = json.dumps(wrapper)
    (OUT_DIR / "HueScenes.deck.json").write_text(deck_json, encoding="utf-8")
    (OUT_DIR / "HueScenes.commands.md").write_text(listing(BUTTONS), encoding="utf-8")
    inject_readme(deck_json)
    ids = [b["button_id"] for b in BUTTONS]
    assert len(ids) == len(set(ids)), "duplicate button ids"

    print(f"wrote {OUT_DIR/'HueScenes.deck.json'} ({len(BUTTONS)} buttons, "
          f"{sum(len(b['command_list']) for b in BUTTONS)} commands)")


if __name__ == "__main__":
    main()
