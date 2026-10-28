# SAMMI deck JSON format notes

Oct 28, 2026 · @Mike Dyer

Reverse-engineered from SAMMI's public docs, the SAMMI Core binary's string table, and exported community decks. Enough to hand-build a deck with `tools/build_deck.py`. SAMMI version at time of writing: 2026.6.0 (string in the binary); the deck declares a 2024.2.0 minimum.

## Deck wrapper (what Copy Deck puts on the clipboard)

```json
{ "deck_data": "<deck object as a JSON *string*>", "unique_id": "2023120201111529375…", "include_image": {} }
```

Deck object keys: `deck_name`, `background_color`, `grid_x`, `grid_y`, `snap_grid`, `adaptive_resizing`, `background_image`, `stretch`, `unique_id`, `sammi_version`, `lb_version`, `button_list`, plus `on`, `encrypted`. Import: side menu → **Paste Deck** (clipboard), or drag a `.txt`/`.json` with this content onto the main window. There is no file-based "Import Deck".

## Button keys

`button_id`, `text`, `color` (BGR decimal), `x`/`y`/`width`/`height` (fractions of the deck, 0–1), `border`, `image`, `persistent`, `queueable`, `overlappable`, `press_type`, `release_duration`, `button_duration`, `init_variable`, `group_id`, `switch_deck`, `deck`, `stretch`, `is_transparent`, `triggers` [], `command_list` [], `release_list` [], `functions`.

`functions` is a cached bitmask: 1 has commands, 16 has triggers, 64 Local Variable Persist, 128 Allow Queue.

## Command entries

Every command: `{"cmd": <id>, "obsid": "Main", "pos": <index>, "vis": 1, "ms": <delay>, "sel": false, "dis": <1 = switched Off>, "xpan": 0, "b0".."bN": <text boxes in doc order>, "v0".."vN": <checkboxes/dropdowns>}`.

The numeric `cmd` is the number in each doc page's `redirect_from: commands/<id>` (repo `SAMMISolutions/docs`). Box order follows the doc table. Ids used by this deck:

| Command | cmd | Boxes |
| --- | --- | --- |
| Comment | 6 | b0 text, v0 color index |
| If Statement | 7 | b0 left, b1 operator, b2 right, v0 block size, v1 else size, v2 condition count; b3…b59 / v3…v22 are the unused extra condition slots (operators default `==`) |
| Repeat | 9 | b0 count, v0 block size |
| Set Local Variable | 15 | b0 name (`global.x` for globals), b1 operator, b2 value (yellow box) |
| Create Object | 16 | b0 |
| Set String Variable | 20 | b0 name, b1 text, v0 relative (append) |
| Trigger Pull Data | 66 | b0 save as, b1 pull key (`amount`, `user_name`, …) |
| Delete Variable | 78 | b0 |
| String to Number | 79 | b0 save as, b1 source variable |
| String Position | 91 | b0 save as, b1 string, b2 search, b3 from, v0 case-insensitive |
| Array Get Size | 100 | b0 array, b1 save as |
| INI: Save Text / Load Text | 126 / 127 | b0 file, b1 section, b2 key, b3 text / save as |
| Trigger Button | 132 | b0 button id, b1 delay ms |
| Overtime | 137 | b0 ms |
| Popup Message | 141 | b0 text, v0 pause button |
| Alert Message | 142 | b0 text |
| Wait Until Variable Exists | 153 | b0 variable, b1 timeout ms |
| Set/Get Object Variable | 165 / 164 | b0 object, b1 key, b2 value / save as |
| Parse Array/Object | 168 | b0 save as, b1 JSON string |
| HTTP Request | 169 | b0 url, b1 method, b2 header object name, b3 body JSON, b4 save as |
| Wait For Timeout | 190 | b0 ms |
| Wait For User Input | 214 | b0 message, b1 default, b2 save as |
| Command Line (current) | 306 | b0 command, b1 save as, plus `"async": 1`. (135 is the deprecated one.) |

**Blocks.** There is no End/Else command. A statement's `v0` is the number of following commands that belong to its block (nested statements count all of their descendants), and an If's `v1` is the size of the else block that follows the then block. Verified against Repeat/If/Switch examples in SAMMI's own docs.

**Async (purple) commands** (HTTP Request, Command Line) fill their save variable later. Pattern: Delete Variable → async command → Wait Until Variable Exists.

**Variables in boxes.** White boxes: `/$var$/`, `/$obj.key[0].name$/`, `/$arr[i]$/` (variable index works). Yellow boxes: bare expressions, strings quoted.

Also used: 83 String Get Length (b0 save, b1 string); 91 String Position v0 = Case Insensitive checkbox; 227 File: Delete File (b0 path); 255 File: Append Text (b0 path, b1 text; creates the file). Command Line runs through cmd.exe (`&&` works), so `start "" notepad.exe file` opens a scrollable list without blocking the button.

## Triggers

Each trigger is an object in the button's `triggers` list with `trg` (type id), `button_id` (must equal the owning button's id), `group_id`, and type-specific keys. Type ids match the Trigger Pull Data "Trigger Type" table in the SAMMI docs. The button's `functions` bitmask must include 16 when the list is non-empty.

| Trigger | JSON |
| --- | --- |
| SAMMI Startup | `{"trg": 10, "type": "SAMMI Startup", "button_id": "...", "group_id": ""}` (confirmed on hardware Oct 28, 2026) |

Platform triggers (chat, redeems, tips…) carry their own key sets; the key names can be read from an exported deck that uses them, or from the string table in `SAMMI Core.exe`. This deck ships none: users attach triggers in SAMMI through Edit Triggers, and SAMMI writes the correct keys itself.

## Sources

- Docs repo: https://github.com/SAMMISolutions/docs (command ids in `redirect_from`), pastebin examples linked from command pages.
- Binary strings: `SAMMI Core.exe` from https://github.com/SAMMISolutions/SAMMI-Official `download/x64.zip`.
- Example decks: `extensions/extension_example.sef` on SAMMISolutions.github.io, prodzpod/SAMMI-Extensions, jspaulsen/spotify-extension.


## Box types (from the command docs legend)

A **yellow** box (marked with an asterisk in the docs tables) accepts a bare variable name, a number, a `"quoted string"`, or math **enclosed in parentheses**, e.g. `(pickNum - nL)`. Set Local Variable's value box, Set Object Variable's value box and the If condition boxes are yellow. A **white** box is literal text with `/$var$/` insertion. Confirmed on hardware Oct 28, 2026: `If okPos > 0`, `If colorMode == 1`, Set Local Variable `i += 1`.
