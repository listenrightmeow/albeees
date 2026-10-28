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
def trigger_button(bid, delay_ms, disabled=False):
    c = cmd(132, b0=bid, b1=str(delay_ms), v0=False)
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


COLOR_BODY_VARS = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"},
                    "color": {"xy": {"x": "@colorX@", "y": "@colorY@"}},
                    "dynamics": {"duration": "@fadeMs@"}}
WHITE_BODY_VARS = {"on": {"on": True}, "dimming": {"brightness": "@brightness@"},
                   "color_temperature": {"mirek": "@whiteMirek@"},
                   "dynamics": {"duration": "@fadeMs@"}}


def put_light_vars(body_vars):
    return f'{CURL} -X PUT {LIGHT_URL} {AUTH} -d "{_vars_body(body_vars)}"'


def light_settings(mode, scene_slot, brightness, color_x, color_y, mirek, fade_ms):
    """The editable block at the top of every action button. Numbers are stored as strings so the
    exact text lands in the JSON (GameMaker would otherwise round 0.6915 when printing)."""
    return [
        comment("SETTINGS - edit the values below, nothing else needs to change.\n"
                "colorMode: 3 = recall a Hue scene (colors are edited in the Hue app; link scenes with 'Hue: Link Scenes'), "
                "1 = fixed color (uses colorX/colorY), 2 = fixed white temperature (uses whiteMirek)\n"
                "sceneSlot: which linked scene this button recalls in mode 3 (1 = the slot 'Hue: Link Scenes' fills)\n"
                "brightness: 1-100 (modes 1 and 2 only)\n"
                "colorX / colorY: CIE xy color, 0-1 each (red 0.6915/0.3083, green 0.17/0.7, blue 0.1532/0.0475, "
                "purple 0.2725/0.1096, orange 0.6/0.38, pink 0.45/0.25)\n"
                "whiteMirek: 153 (cool daylight) to 500 (very warm); 370 = warm white, 250 = neutral\n"
                "fadeMs: how long the bulb takes to change, in milliseconds (modes 1 and 2)", 2),
        set_local("colorMode", str(mode)),
        set_string("sceneSlot", scene_slot),
        set_string("brightness", str(brightness)),
        set_string("colorX", str(color_x)),
        set_string("colorY", str(color_y)),
        set_string("whiteMirek", str(mirek)),
        set_string("fadeMs", str(fade_ms)),
        comment("END OF SETTINGS. The commands below read the variables above.", 2),
    ]


def apply_light():
    """Send the request that matches colorMode, capture the bridge's reply, and alert on failure so a
    misconfigured button says why instead of silently doing nothing."""
    recall = f'{CURL} -X PUT {SCENE_URL} {AUTH} -d "{cmd_json({"recall": {"action": "active"}})}"'
    def send(command):
        return [delete_var("resp"), shell(command, "resp"), wait_exists("resp", 10000)]
    return [
        set_string("resp", ""),
        if_("colorMode", "==", "1", send(put_light_vars(COLOR_BODY_VARS))),
        if_("colorMode", "==", "2", send(put_light_vars(WHITE_BODY_VARS))),
        if_("colorMode", "==", "3", [
            ini_load("scene_/$sceneSlot$/", "hueSceneId"),
            if_("hueSceneId", "==", "0", [
                alert("Hue: no scene linked for slot /$sceneSlot$/. Run 'Hue: Link Scenes' first."),
            ]),
            *send(recall),
        ]),
        str_len("respLen", "/$resp$/"),
        if_("respLen", "==", "0", [
            alert("Hue: no reply from the bridge (bridge off, wrong IP, or colorMode is not 1, 2 or 3). Run Hue 1: Discover, then Hue 4: Test."),
        ]),
        str_pos("errPos", "/$resp$/", '"description"'),
        if_("errPos", ">", "0", [
            alert("Hue rejected the request: /$resp$/"),
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


def scene_group_name(num_var, save_var):
    """Set `save_var` to "Room name (room)" / "Zone name (zone)" for the scene at scenes.data[num_var]."""
    out = [set_string(save_var, "unknown room")]
    for groups, label in (("rooms", "room"), ("zones", "zone")):
        out += [
            set_local("r", "0"),
            repeat("nR" if groups == "rooms" else "nZ", [
                str_pos("same", f"/$scenes.data[{num_var}].group.rid$/", f"/${groups}.data[r].id$/"),
                if_("same", ">", "0", [
                    set_string(save_var, f"/${groups}.data[r].metadata.name$/ ({label})"),
                ]),
                set_local("r", "1", op="+="),
            ]),
        ]
    return out


LOAD_ALL = lambda: [ini_load("ip", "hueIp"), ini_load("key", "hueKey"),
                    ini_load("light", "hueLightId"), ini_load("light_type", "hueLightType")]
SCENE_SLOTS = [("1", "Scene 1")]   # one example slot; add ("2", "Scene 2") etc. and a matching action button for more


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
def button(bid, text, x, y, color, commands, triggers=(), w=0.25, h=0.125, queueable=False, persistent=False):
    cmds = number(flatten(commands))
    trg = [dict(t, button_id=bid) for t in triggers]
    functions = (1 if cmds else 0) + (16 if trg else 0) + (64 if persistent else 0) + (128 if queueable else 0)
    return {
        "color": color, "persistent": 1.0 if persistent else 0.0, "text": text,
        "release_duration": 0.0, "queueable": 1.0 if queueable else 0.0,
        "command_list": cmds, "press_type": 0.0, "x": x, "border": 2.0, "image": "",
        "triggers": trg, "group_id": "", "overlappable": 0.0, "init_variable": "",
        "deck": 0.0, "width": w, "button_id": bid, "button_duration": 0.0, "y": y,
        "switch_deck": "", "height": h, "release_list": [], "functions": float(functions),
        "stretch": 0.0, "is_transparent": 0.0,
    }


STARTUP_TRIGGER = {"trg": 10.0, "type": "SAMMI Startup", "group_id": ""}


def action_button(bid, text, x, color, *, mode=3, scene_slot, brightness=100,
                 color_x="0.6915", color_y="0.3083", mirek="370", fade_ms="300"):
    """An action button with no trigger of its own. The user attaches whatever SAMMI trigger they
    like (right-click > Edit Triggers): a chat command, a redeem, a tip alert, a hotkey, a timer.
    Two examples ship: one that recalls a Hue scene (mode 3) and one with a raw color (mode 1)."""
    return button(bid, text, x, 0.5, color, [
        comment("ACTION BUTTON. Attach any trigger to it: right-click the button > Edit Triggers. "
                "When it fires it reads the bridge settings from the ini file, sends one request to the bridge, "
                "then holds the button 1 s so bursts of events stay under Hue's rate limit "
                "(1 command/s for rooms, zones and scenes). Events that arrive meanwhile queue up and run in order.", 1),
        *light_settings(mode, scene_slot, brightness, color_x, color_y, mirek, fade_ms),
        *LOAD_ALL(),
        *apply_light(),
        overtime(1000),
        trigger_button("hueReset", 10000, disabled=True),   # optional: turn "Off" to enable the 10 s auto-reset
    ], queueable=True)


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
            parse("rooms", "/$resp2$/"),
            delete_var("resp3"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/zone" -H "hue-application-key: /$hueKey$/"', "resp3"),
            wait_exists("resp3", 10000),
            parse("zones", "/$resp3$/"),
            arr_size("lights.data", "nL"),
            arr_size("rooms.data", "nR"),
            arr_size("zones.data", "nZ"),
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
            set_local("kind", "0"),
            set_local("idx", "pickNum"),
            if_("pickNum", ">=", "nL", [set_local("kind", "1"), set_local("idx", "(pickNum - nL)")]),
            if_("pickNum", ">=", "(nL + nR)", [set_local("kind", "2"), set_local("idx", "(pickNum - nL - nR)")]),
            if_("kind", "==", "0", [
                ini_save("light", "/$lights.data[idx].id$/"),
                ini_save("light_type", "light"),
                ini_save("light_name", "/$lights.data[idx].metadata.name$/ (bulb)"),
                ini_save("group_id", "none"),
            ]),
            if_("kind", "==", "1", [
                ini_save("light", "/$rooms.data[idx].services[0].rid$/"),
                ini_save("light_type", "grouped_light"),
                ini_save("light_name", "/$rooms.data[idx].metadata.name$/ (room)"),
                ini_save("group_id", "/$rooms.data[idx].id$/"),
            ]),
            if_("kind", "==", "2", [
                ini_save("light", "/$zones.data[idx].services[0].rid$/"),
                ini_save("light_type", "grouped_light"),
                ini_save("light_name", "/$zones.data[idx].metadata.name$/ (zone)"),
                ini_save("group_id", "/$zones.data[idx].id$/"),
            ]),
            ini_load("light_name", "hueLightName"),
            alert("Action buttons will control '/$hueLightName$/' (saved to the ini file)"),
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
              "Linked scenes (used by colorMode 3):\n"
              + "".join(f"  {label}: /$scene_{slot}$/\n" for slot, label in SCENE_SLOTS)
              + "\nA value of 0 means it has not been set yet.", pause=False),
    ]),
    button("hueScenes", "Hue: Link\nScenes", 0.25, 0.25, TEAL, [
        comment("The user creates a scene in the Hue app (any colors, any number of bulbs in the room or zone). "
                "This button lists the bridge's scenes and links each button to one of them. Scene buttons in colorMode 3 "
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
            parse("rooms", "/$resp2$/"),
            delete_var("resp3"),
            shell(f'{CURL} "https:///$hueIp$//clip/v2/resource/zone" -H "hue-application-key: /$hueKey$/"', "resp3"),
            wait_exists("resp3", 10000),
            parse("zones", "/$resp3$/"),
            arr_size("rooms.data", "nR"),
            arr_size("zones.data", "nZ"),
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
                if_(f"num{slot}", ">=", "0", [
                    *scene_group_name(f"num{slot}", "groupName"),
                    ini_save(f"scene_{slot}", f"/$scenes.data[num{slot}].id$/"),
                    ini_save(f"scene_{slot}_name", f"/$scenes.data[num{slot}].metadata.name$/ in /$groupName$/"),
                    alert(f"{label} -> scene '/$scenes.data[num{slot}].metadata.name$/' in /$groupName$/. "
                          "Recalling it changes every light in that room/zone, whatever Hue 3 picked."),
                ]),
            ]],
            alert("Scene link saved. Check it with Hue: Show Settings, then run 'Example: Hue scene'."),
        ], [
            popup("Could not list the scenes.\n\nBridge said: /$resp$/\n\n"
                  "'unauthorized user' = run Hue 2: Pair again. Empty = wrong IP or bridge off."),
        ]),
    ]),
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
              "The bottom row holds two example action buttons with no trigger attached. Attach any trigger to them "
              "(right-click > Edit Triggers), or copy them to make more.\n"
              "'Example: Hue scene' recalls the scene linked with Hue: Link Scenes, so you change its look in the Hue app. "
              "A scene always acts on the lights of its own room/zone, not on the Hue 3 target.\n"
              "'Example: raw color (red)' sets a fixed color from its SETTINGS block (right-click > Edit Commands): "
              "colorMode 1 = xy color, 2 = white temperature, 3 = Hue scene.\n\n"
              "Lights stopped reacting? Click Hue 1: Discover, then Hue 4: Test.", pause=False),
    ]),

    # --- row 4: example action buttons (no triggers shipped) -------------------------------------------------
    action_button("hueScene1", "Example:\nHue scene", 0.0, TEAL,
                  scene_slot="1"),                                                        # mode 3: recalls the linked scene
    action_button("hueColorRed", "Example:\nraw color (red)", 0.25, RED,
                  mode=1, scene_slot="1", brightness=100, color_x="0.6915", color_y="0.3083"),
    button("hueReset", "Reset\n(optional)", 0.5, 0.5, GRAY, [
        comment("Restores neutral white. Not triggered by anything unless you enable the disabled "
                "'Trigger Button' command at the end of each action button (10 s delay).", 1),
        *light_settings(2, "1", 60, "0.3127", "0.3290", "250", "1000"),
        *LOAD_ALL(),
        *apply_light(),
    ]),
]


# ----------------------------------------------------------------------------
# readable listing
# ----------------------------------------------------------------------------
NAMES = {83: "String Get Length", 255: "File: Append Text", 227: "File: Delete File", 6: "Comment", 142: "Alert Message", 141: "Popup Message", 78: "Delete Variable", 306: "Command Line",
         153: "Wait Until Variable Exists", 190: "Wait For Timeout", 168: "Parse Array/Object", 15: "Set Local Variable",
         20: "Set String Variable", 91: "String Position", 126: "INI: Save Text", 127: "INI: Load Text",
         214: "Wait For User Input", 79: "String to Number", 100: "Array Get Size", 137: "Overtime",
         169: "HTTP Request", 132: "Trigger Button", 7: "If", 9: "Repeat"}


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
    if i == 132: return f"Trigger Button `{b(0)}` after {b(1)} ms"
    if i == 7:   return f"If `{b(0)}` {b(1)} `{b(2)}`  (block {int(c['v0'])}, else {int(c.get('v1', 0))})"
    if i == 9:   return f"Repeat `{b(0)}` times  (block {int(c['v0'])})"
    return f"cmd {i}"


def listing(buttons):
    lines = [f"# {DECK_NAME} deck, command listing", "",
             "Generated by `tools/build_deck.py`. Paste `deck/HueScenes.deck.json` into SAMMI with side menu > Paste Deck.",
             f"Settings file: `{INI}` in the SAMMI folder, section `[{SEC}]`, keys `ip`, `key`, `light`, `light_type`, `light_name`, `scene_<slot>`.", ""]
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
