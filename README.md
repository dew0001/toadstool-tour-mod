# Toadstool Tour Mod

A mod for **Mario Golf: Toadstool Tour** (GameCube, USA) that you play in [Dolphin](https://dolphin-emu.org).

- **Widescreen built in:** real 16:9 with a correctly shaped HUD. No cheats or special Dolphin settings needed.
- **Everything unlocked:** every course and character from the start.
- **Separate entry:** shows up in Dolphin as *Mario Golf: Toadstool Tour (Mod vN)* with its own game ID (GFTEMD) and save, next to your normal copy.
- **Sharper HUD:** optional HD UI textures by NickPancakes, installed automatically.
- **Automatic updates:** `Play.bat` checks for a new version every time you start the game.

This repo contains **no game data**. The mod is built on your PC from **your own copy** of the game, and every player ends up with a byte-identical result, so online play stays in sync.

## Setup (once)

1. Install Dolphin. To play online together, everyone needs the **same Dolphin version**; the current one for this group is listed in [`mod/latest.json`](mod/latest.json) under `dolphin`.
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
- **HD UI textures:** "Toadstool Tour 4x" by NickPancakes ([Dolphin forum thread](https://forums.dolphin-emu.org/Thread-mario-golf-toadstool-tour-gcn-4x-ui-texture-pack)). Downloaded from the author's own link, not re-hosted here.

Please don't share game files (.iso and similar). Share this repo; everyone builds from their own copy.

## For the maintainer

`dev/` holds the tools that decode the game's files and build the mod; see [`dev/README.md`](dev/README.md). To publish version N, run `dev\publish.ps1`, then commit and push. Everyone's next `Play.bat` picks it up.
