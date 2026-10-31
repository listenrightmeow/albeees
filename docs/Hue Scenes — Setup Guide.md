# Hue Scenes — Setup Guide

Oct 27, 2026 · @Mike Dyer

For the one-time remote install. You drive his PC; he presses one button on the Hue Bridge. Plan on 20–30 minutes. No SAMMI knowledge needed beyond what is written here.

## Before the call

Have these ready so the session is only clicking.

- [ ] The deck file `deck/HueScenes.deck.json` in a place you can download onto his PC (email, Drive link). It is plain text; SAMMI imports it from the clipboard.
- [ ] Open a Command Prompt on his PC during the call and run `where curl.exe`. It must print a path (ships with Windows 10 1803+ and Windows 11). The deck sends every Hue command through `curl.exe`.
- [ ] Text him: "We'll need you at your PC for 20 minutes, with your phone, and able to reach the white Hue Bridge puck. I'll remote in with Windows Quick Assist."
- [ ] Confirm he has SAMMI installed (2024.2.0 or newer) and his streaming platform account linked in SAMMI, so its events can be used as triggers.
- [ ] Know what the action buttons should control: one bulb, a whole room, or a zone. If only some bulbs in a room should react, he creates a **zone** in the Hue app first (Settings → Rooms & zones → Create zone → tick the bulbs) and names it something like "Stream lights".
- [ ] Ask him to make the scenes before the call, in the Hue app, on that room or zone: a scene named **Scene 1** (any colors he likes), and a second one named **Scene 2** if he wants the scene sequence example. Up to four scenes can be linked. Each scene must be made on the room or zone that holds the lights he wants to react: a Hue scene only ever changes the lights of its own room or zone. He picks any colors and brightness he likes with the app's color wheel. Changing a color later is editing that scene, so SAMMI never needs touching again. The Hue app cannot put effects (candle, fire and the like) or breathe pulses into a scene. The deck adds those on top, so the scene only needs colors and brightness.
- [ ] Decide what should fire the example buttons he wants, for example **Example: Hue scene** and **Example: color (red)**: a chat command, a redeem, a tip alert, a hotkey, anything SAMMI offers as a trigger. The deck ships every button with no trigger attached; you add them in Part D.
- [ ] Ask whether SAMMI already has a **Hue Scenes** deck from an earlier install. If so, you delete it before pasting the new one (Part B).

SAMMI words you'll see: a **deck** is a page of buttons; a **button** holds a list of **commands** that run top to bottom; a **trigger** is what fires a button (a chat command, a redeem, a keypress). That is all you need.

## Part A — Get on his PC

Windows Quick Assist is built in on both sides; nothing to install.

1. On your PC: press **Win + Ctrl + Q** (or search "Quick Assist"), click **Help someone**, sign in with a Microsoft account, and read him the 6-digit code.
2. On his PC he presses **Win + Ctrl + Q**, types the code, clicks **Submit**, then **Allow** when asked.
3. Click **Request control**; he clicks **Allow** again. You now drive his screen.

If Quick Assist is blocked on either side, AnyDesk or Parsec work the same way: he installs, reads you an ID, approves.

## Part B — Put the deck into SAMMI

1. Download `HueScenes.deck.json` onto his PC (Desktop is fine).
2. Open it in Notepad, press **Ctrl+A** then **Ctrl+C**. The whole file is now on the clipboard.
3. Open **SAMMI Core** if it isn't running (desktop icon or Start menu).
4. If a deck named **Hue Scenes** is already there from an earlier version, delete that deck first. Pasting over it leaves old buttons behind.
5. In SAMMI's side menu, click **Paste Deck**. (Dragging the file onto SAMMI's main window does the same.)
6. A deck named **Hue Scenes** appears with 23 buttons. Double-click it to open it. You should see:
   - Row 1: **Hue 1: Discover**, **Hue 2: Pair**, **Hue 3: Pick Target**, **Hue 4: Test**
   - Row 2: **Hue 5: Probe**, **Hue Config: Set IP**, **Hue: Show Settings**, **Hue Scenes: how it works**
   - Row 3: **Hue: Auto rediscover**, **Hue: Link Scenes**, **Hue: Try Action**, **Hue: apply (shared)**
   - Below a gap, the example buttons: **Example: Hue scene**, **Example: color (red)**, **Reset**, **Example: effect (candle)**; **Example: scene + candle**, **Example: orange + fire**, **Example: breathe x3**, **Example: turn off**; **Example: turn on**, **Example: scene sequence**, **Hue: Stop sequence**.
7. **Hue: apply (shared)** does the work for every action button. Each action button only holds its settings and calls it. Never press it and never attach a trigger to it.
8. Right-click **Example: Hue scene** → **Edit Triggers**. The list is empty on purpose; the triggers are added in Part D once the lights work.
9. Click **Save** at the top of the deck window. (SAMMI needs Save pressed to keep changes; do it whenever you see the button.)

## Part C — Connect the light

Five buttons, clicked in order. To click a button so it runs: right-click it → **Edit Commands** → press **Run Button** at the bottom. (Or open the SAMMI Panel and click it there; either works.)

| Step | You click | He does | You should see |
| --- | --- | --- | --- |
| 1 | **Hue 1: Discover** | Nothing | A yellow message at the bottom of SAMMI: "Hue bridge at 192.168.x.x (saved to the ini file)" |
| 2 | **Hue 2: Pair** | When the pop-up says so: walks to the Hue Bridge and presses the big round button on top, then says "done" | You click **OK** on the pop-up within 30 seconds of his press. Message: "Paired. App key saved to the ini file." |
| 3 | **Hue 3: Pick Target** | Tells you which name is right | A Notepad window opens listing every bulb, then every room, then every zone as "0 = Name (bulb)", "5 = Living room (room, every bulb in it)"… (SAMMI's own popup cannot scroll, so the list goes to a text file.) Type the number into the small SAMMI popup, click OK. Message: "Action buttons will control 'Name' (saved to the ini file)". A number that is not on the list changes nothing; the message says so, and you run Hue 3 again. |
| 4 | **Hue 4: Test** | Watches the lights | The bulb(s) pulse (breathe) once; message shows the bridge's reply |
| 5 | **Hue: Link Scenes** (third row) | Confirms which scene is which | First popup: type part of a scene name to narrow the list (e.g. `Scene`), or leave it empty for all. A Notepad window then opens with the matching scenes grouped under their room or zone, e.g. "== Stream lights (zone) ==" then "12 = Scene 1". The group picked in Hue 3 is marked "<-- the target picked in Hue 3"; choose scenes from that group. Four SAMMI popups follow, one for each slot, **Scene 1** to **Scene 4**. Type a number, or -1 to skip that slot. Message per slot: "Scene 1 -> scene 'Scene 1' in Stream lights (zone)…", then "Scene links saved." |
| 6 (optional) | **Hue: Try Action** (third row) | Watches the lights | A Notepad window lists what the Hue 3 target can do: named colors, whites, turn on, turn off, then the alerts, signals, effects and timed effects the bridge reports for it. Type a number; the lights do it. Message: "Sent. To put this on an action button, copy an Example button and set: …" with the settings to use. Signals and timed effects exist only here; no button setting covers them. |
| 7 (optional) | **Hue 5: Probe** | Nothing | A pop-up with either bridge config JSON or a red SAMMI HTTP error. Either is fine; note which one you got for the plan. |

If step 1 shows the "Could not find the bridge" pop-up: ask him to open the Hue app on his phone → Settings → My Hue System → tap the bridge → read you the IP address. Click **Hue Config: Set IP**, type it into the pop-up, OK, then run step 2. **Hue: Show Settings** displays what is saved at any time.

If step 2 says "link button not pressed": he presses the bridge button again and you click **Hue 2: Pair** again straight away.

If step 4 does nothing: run **Hue 3: Pick Target** again and choose a different name — the first pick was probably a different bulb or room.

If step 5 lists nothing with your filter, run it again with the filter box empty. If it does not list his scenes at all: he has not made them yet, or made them on a different room. Hue app → the room or zone → Scenes → **+** → pick colors → name it. Then run **Hue: Link Scenes** again. **Hue: Show Settings** shows what is linked.

If you replaced an older Hue Scenes deck: run **Hue 3: Pick Target** once more and **Hue: Link Scenes** once more, even if Show Settings already shows values. The new deck saves extra settings (whether the target is a room or a zone, and each scene's room) that the old one did not.

## Part D — Attach the triggers and prove it

1. Run **Example: Hue scene** and **Example: color (red)** with **Run Button** the same way as above; the lights should switch to the scene, then go red, each within a second. Run **Reset** last to put them back to neutral white and stop any effect. Success is silent. Only a problem shows an alert.
2. If he wants effects, also try **Example: effect (candle)** and **Example: scene + candle**, then **Reset**. For **Example: scene sequence** he needs Scene 1 and Scene 2 linked; **Hue: Stop sequence** stops it.
3. Right-click **Example: Hue scene** → **Edit Triggers** → **Add**. Pick the event from his platform that should fire it (SAMMI lists every event the linked account provides) and fill in the condition: the chat command text, the redeem name, a minimum amount, whatever that event uses. Repeat for every other example button he wants, or copy an example button for every extra look he wants and change its settings (below).
4. Fire a test event. SAMMI Bridge has a test-trigger tab for most platform events, which sends a fake event into SAMMI without anything happening on the live channel. The matching button blinks in SAMMI and the lights change. If his platform has no test trigger, do the real thing once.
5. Click **Save** on the deck.

### Changing what an action button does

Right-click the button → **Edit Commands**. The first commands are a **SETTINGS** block. Change only the values there:

| Setting | Values |
| --- | --- |
| `look` | `scene`, `color`, `white`, `on`, `off` or `none` (none keeps the current look and only runs the effect) |
| `lookValue` | scene: the slot number, 1 to 4. color: `red`, `orange`, `yellow`, `green`, `cyan`, `blue`, `purple`, `pink`, or x,y such as `0.6915,0.3083`. white: `warm`, `neutral`, `cool`, or a number from 153 (cool) to 500 (warm). off: empty for the Hue 3 target, or a scene slot to turn off that scene's room. on / none: empty |
| `brightness` | 1 to 100 (color, white, on) |
| `effect` | `none`, `breathe`, `candle`, `fire`, `prism`, `sparkle`, `opal`, `glisten`, `underwater`, `cosmos`, `sunbeam`, `enchant`, `stop` |
| `pulses` | How many breathe pulses, about 2 seconds apart (effect `breathe`) |
| `speed` | 0 (slow) to 1 (fast), for candle, fire and the others |

Effects run bulb by bulb. With a scene, each bulb of the scene runs it in its own scene color; bulbs that cannot run effects, or that the scene left off, are skipped. Otherwise it runs on the Hue 3 bulb, or on every bulb of its room or zone. An effect runs until **Reset** (effect `stop`) or another effect.

Each action button ends with a switched-off command that runs **Reset** after 10 s. Turn it on to get an automatic reset.

**Example: scene sequence** has its own settings: `scene1` and `scene2` (linked slots; leave `scene2` empty for one scene), `effect1` and `effect2`, `seconds1` and `seconds2`, `whenDone` (`loop`, `off` or `stay`) and `maxMinutes` (with loop: turn off and stop after that many minutes; 0 = until stopped). Starting a sequence stops any other one. **Hue: Stop sequence** stops it and drops steps still waiting in line. For more than two scenes, chain sequence buttons with triggers.

Leave every action button's **Persistent Variables** on; **Hue: apply (shared)** reads the settings from the button that called it.

## Part E — Leave it in a safe state

1. In SAMMI's settings for his linked platform account, make sure auto-connect is ticked so it reconnects by itself after a reboot.
2. Copy the deck file to a second place (your own machine) as the backup.
3. Copy `hue_scenes.ini` from his SAMMI folder next to your deck backup (it holds the bridge IP, app key, target id and the scene links).
4. Send him the maintenance note (`docs/Hue Scenes — Maintenance Note.md`) and tell him the one thing to remember: "If the lights ever stop reacting, open SAMMI, click **Hue 1: Discover** then **Hue 4: Test**. If the test doesn't pulse, text me."
5. End the Quick Assist session.

## If something goes wrong

| What you see | Likely cause | Fix |
| --- | --- | --- |
| Any Hue button shows "'curl.exe' is not recognized" | Very old Windows 10 without curl | Run Windows Update, or install curl from curl.se and put it on the PATH |
| Pair / Test pop-up shows an empty response | Wrong IP, bridge off, or PC and bridge on different networks | Hue: Show Settings → check IP; ping it from a Command Prompt; Hue Config: Set IP |
| "link button not pressed" | More than 30 s passed | He presses the button again; click Pair immediately |
| An action button shows "Hue rejected the look: …" | The bridge refused it; the message is Hue's own error (wrong scene id, light not found, unauthorized) | Read the description: `unauthorized` → Hue 2: Pair; `not found` → Hue 3: Pick Target or Hue: Link Scenes again |
| "Hue: unknown look", "unknown color" or "unknown effect" | A typo in the button's SETTINGS block | Edit Commands → fix the value; the alert lists the allowed ones |
| "Hue: no reply from the bridge" | Bridge off or wrong IP | Hue 1: Discover, then Hue 4: Test |
| Example: Hue scene flashes, no error, the lights you watch don't change | The linked scene belongs to a different room or zone, so those lights changed instead | Run **Hue: Link Scenes** and pick a scene under the heading marked as the Hue 3 target, or make the scene on the right room/zone in the Hue app. **Hue: Show Settings** shows which room the linked scene is in |
| "Hue: no scene linked for slot 1" | No scene linked in that slot (Show Settings shows 0), or he deleted and recreated the scene | Run **Hue: Link Scenes** and pick the scene for that slot |
| "Hue: found no bulbs for the effect" or "could not read the Hue 3 target's room or zone" | Target saved by an older deck, or the room/zone changed | Run **Hue 3: Pick Target** again |
| "Hue: no bulb took the effect" | None of the bulbs can run effects, or the bridge refused | Use a color or breathe instead; **Hue: Try Action** shows which effects the target lists |
| "'Hue: apply (shared)' runs when an action button calls it" | Someone pressed the shared button | Press an action button instead |
| Old buttons still in the deck after an update | The new deck was pasted over the old one | Delete the Hue Scenes deck, paste again, then run Hue 3 and Hue: Link Scenes once more |
| Pair worked but Test does nothing | Wrong target chosen, or bulb is off at the wall switch | Run Pick Target again; check the physical switch is on |
| Run Button works but the live event does nothing | SAMMI not connected to the platform, or the trigger's condition does not match what the event sends | Bottom-left of SAMMI: the platform must show green; reconnect it. Then right-click the button → Edit Triggers and compare the condition with the real event |
| Everything worked, now broken days later | Bridge got a new IP from the router | Click Hue 1: Discover, then Hue 4: Test (Hue: Auto rediscover also does this 15 s after SAMMI starts) |
| Message says "unauthorized user" | App key lost (bridge reset) | He presses the bridge button; click Hue 2: Pair |
