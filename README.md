# Toadstool Tour Mod

A mod for **Mario Golf: Toadstool Tour** (GameCube, USA) that you play in [Dolphin](https://dolphin-emu.org).

- **Widescreen built in:** real 16:9 with the HUD out at the screen edges, every piece in its proper shape. No cheats or special Dolphin settings needed.
- **Everything unlocked:** every course and character from the start.
- **TV-style cameras:** after you hit, the camera cuts to behind and above the ball and follows it all the way. Putts are aimed, stroked and followed from behind the ball, down the line.
- **Hold A to fast-forward** the ball after you hit (about 3× speed). The ball ends up exactly where it would have.
- **No intro movie** and no shattered-glass screen effect.
- **Replays ask first:** B after a shot opens *Continue / Watch Replay* instead of replaying straight away. Only the player who hit can open it.
- **Club Slots:** the item reel no longer has *Double the points*; its slots went to the other four items.
- **Separate entry:** shows up in Dolphin as *Mario Golf: Toadstool Tour (Mod vN)* with its own game ID (GFTEMD) and save, next to your normal copy.
- **Fullscreen and sharp:** starts fullscreen over the whole screen (Alt+Enter for a window) at a resolution that fits your screen, with HD UI textures by NickPancakes installed automatically.
- **Automatic updates:** `Play.bat` checks for a new version every time you start the game.

## Controls (Xbox or PlayStation-style controller on Port 1)

| Control | Does |
| --- | --- |
| Left stick left/right | Aim |
| Left stick up/down | Power: moves the landing spot farther/closer (and the power gauge with it); tilt further to move it faster |
| LB / RB | Change club |
| LT / RT | Switch views (RT looks down to the hole or landing spot) |
| Right stick | Turn the camera; up/down also sets the power |
| View / Back | Side view while held |
| A | Swing; hold after the hit to fast-forward |

Every way of looking around still works on putts: the camera goes back down the line when you let go. These controls are set up for the modded game only, from your own Port 1 controller settings; other games keep yours.

This repo contains **no game data**. The mod is built on your PC from **your own copy** of the game, and every player ends up with a byte-identical result, so online play stays in sync.

## Setup (once)

1. Install Dolphin. To play online together, everyone needs the **same Dolphin version**; the current one for this group is listed in [`mod/latest.json`](mod/latest.json) under `dolphin`. If Dolphin offers to update itself, say no.
2. Make sure your own Toadstool Tour (USA) file is in one of Dolphin's game folders. `.iso`, `.gcm` and `.ciso` work as-is. For `.rvz` or `.gcz`, right-click the game in Dolphin, choose **Convert File...**, and pick ISO.
3. Download this repo: **Code → Download ZIP**, then unzip it anywhere (for example `Documents\Toadstool Tour Mod`).
   - If Windows warns about the download, right-click the zip, choose **Properties**, tick **Unblock**, then unzip.

## Playing

Double-click **`Play.bat`**. The first time, it:

1. Finds your copy of the game through Dolphin's game folders (or asks you to pick it).
2. Checks it's the clean USA game and builds *Mario Golf - Toadstool Tour (Mod).iso* next to it. This takes about a minute.
3. Installs the HD textures and starts the game.

After that, `Play.bat` just starts the game, and rebuilds it first whenever there's a new version. Your original game file is never changed.

`Update only.bat` does the update without starting the game. That's handy right before an online session.

## Playing online (Dolphin NetPlay)

Up to 4 players. Everyone needs the latest mod version (run `Play.bat` or `Update only.bat` first), the same Dolphin version, and their controller set up under **Controllers → Port 1**.

**Host:**
1. **Tools → Start NetPlay... → Host**.
2. Pick *Mario Golf: Toadstool Tour (Mod vN)* and click **Host**.
3. Send friends the **Host Code**.
4. When everyone's in: **Assign Controller Ports**, set **Buffer** (start around 6, lower it if smooth), then **Start**.

**Friends:**
1. **Tools → Start NetPlay... → Connect**.
2. Choose **Traversal Server**, paste the Host Code, and click **Connect**.

If a player shows as not having the game, their mod version or Dolphin version doesn't match. Have them run `Update only.bat`.

## Credits

- **Widescreen:** based on gamemasterplc's 16:9 Gecko code from the Dolphin wiki, rebuilt as a permanent patch.
- **Cameras, fast-forward, no intro:** written for this mod.
- **HD UI textures:** "Toadstool Tour 4x" by NickPancakes ([Dolphin forum thread](https://forums.dolphin-emu.org/Thread-mario-golf-toadstool-tour-gcn-4x-ui-texture-pack)). Downloaded from the author's own link, not re-hosted here.

Please don't share game files (.iso and similar). Share this repo; everyone builds from their own copy.

## For the maintainer

`dev/` holds the tools that decode the game's files and build the mod; see [`dev/README.md`](dev/README.md). To publish version N, run `dev\publish.ps1`, then commit and push. Everyone's next `Play.bat` picks it up.
