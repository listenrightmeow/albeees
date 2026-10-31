# Hue Scenes — Maintenance Note

Oct 28, 2026 · @Mike Dyer

For the person whose lights these are. Keep this somewhere you can find it. Everything below is in SAMMI, in the deck called **Hue Scenes**.

## What it does

The example buttons in SAMMI change your Hue lights. **Example: Hue scene** switches them to a scene from your Hue app; **Example: color (red)** sets a fixed color. Others add an effect such as candle or fire, pulse the lights, turn them on or off, or play two scenes in a loop (**Example: scene sequence**, stopped with **Hue: Stop sequence**). **Reset** puts them back to neutral white. Whatever trigger was attached to each button during setup (a chat command, a redeem, a tip, a hotkey) fires it. SAMMI sends small commands to the Hue Bridge in your room. Nothing goes through the cloud. When it works, nothing pops up; a message only appears when something is wrong.

## The one fix to try first

If the lights stop reacting:

1. Open SAMMI.
2. Open the **Hue Scenes** deck.
3. Right-click **Hue 1: Discover** → Edit Commands → **Run Button**. A message at the bottom should say "Hue bridge at 192.168…".
4. Right-click **Hue 4: Test** → Run Button. The lights should pulse once.

If they pulse, you are done. If not, text Mike.

## Things that can break it, and what they look like

| What happened | What you see | What to do |
| --- | --- | --- |
| Router gave the bridge a new address | Nothing happens on events; Test does nothing | Run **Hue 1: Discover**, then **Hue 4: Test** (SAMMI also does this by itself 15 s after it starts) |
| Bridge was reset or replaced | Test says "unauthorized user" | Press the round button on the bridge, then run **Hue 2: Pair** within 30 s |
| SAMMI lost its connection to your streaming platform | Test works, live events do nothing | Bottom-left of SAMMI: the platform must show green. Reconnect it |
| Bulb is off at the wall switch | Test does nothing, no error | Turn the switch on |
| A linked scene was deleted in the Hue app | Test works, that one button does nothing or says "no scene linked" | Make the scene again, then run **Hue: Link Scenes** and type its number (or text Mike) |
| An effect such as candle keeps running | The lights flicker after the event | Run **Reset**; it stops the effect |
| A scene sequence keeps going | The scenes keep switching | Run **Hue: Stop sequence** |
| SAMMI was reinstalled | Deck is gone | Text Mike; he has a backup of the deck |

## Want different colors?

You do not need SAMMI for this. Open the Hue app, go to the room or zone the lights are in, open the scene that **Example: Hue scene** recalls (it is named **Scene 1** unless you renamed it), and change the colors, brightness or which bulbs it includes. The next event uses the new look. Just don't delete and recreate a scene; if you do, run **Hue: Link Scenes** or text Mike. A scene changes the lights of the room or zone it belongs to, so keep it on the room or zone that holds the lights you want.

## Want a different trigger, or another button?

Right-click an example button → **Edit Triggers** to change what fires it. For another button, right-click one of the examples → Copy, paste it into the deck, then change its trigger and its SETTINGS; or text Mike.

Not sure what your lights can do? Run **Hue: Try Action**. It lists what they support in Notepad, plays the one you pick, and tells you which settings put it on a button.

If you are comfortable in SAMMI: right-click an example button → Edit Commands. The first few commands are a **SETTINGS** block, with the allowed values in the comment above them. `look` is `scene`, `color`, `white`, `on`, `off` or `none`. `lookValue` is the scene slot (1-4), a color name such as `red` or `blue`, or a white such as `warm` (153 cool to 500 warm). `brightness` is 1-100. `effect` is `none`, `breathe`, `candle`, `fire` or one of the others listed, or `stop`. Leave everything below the "END OF SETTINGS" comment alone.

## Please don't

- Don't delete or rename buttons in the Hue Scenes deck.
- Don't press **Hue: apply (shared)** or attach a trigger to it. Every action button uses it.
- Don't turn off **Persistent Variables** on an action button. The shared button reads the settings from it.
- Don't delete the file `hue_scenes.ini` in the SAMMI folder. It holds the bridge address, the app key, which lights to use and which scene each button recalls.
- Don't rename or delete the linked scenes in the Hue app. Editing their colors is fine and encouraged.
