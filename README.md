# Toadstool Tour Mod

A mod for **Mario Golf: Toadstool Tour** (GameCube, USA) that you play in [Dolphin](https://dolphin-emu.org).

- **Widescreen built in:** real 16:9 with the HUD out at the screen edges, every piece in its proper shape. No cheats or special Dolphin settings needed.
- **Everything unlocked:** every course and character from the start.
- **Shy Guy joins the roster** as a 17th golfer, with everyone else unchanged: on the character select screen, press Down from the bottom row to the *More* page. He's the Shy Guy from *Mario Power Tennis*, with his own pictures, name, stats (205 yards, high shots, the narrowest impact window, top control, strong spin), voice (his lines when you land on him and pick him on the select screen, cheers and groans at the end of each hole, chirps while others line up their shots) and power shot: a burst of red and white stars with his special-shot shout. He swings with Koopa Troopa's animations.
- **Tony the Tiger joins too**, right of Shy Guy on the *More* page: tall and powerfully built, in his red bandana, smoothly animated with Waluigi's swing and moves. He's a high-risk, high-reward pick: a 350-yard driver (50 past the longest Star version; his other clubs scale with it) with high shots, the best control and strong spin, but a swing meter that runs twice as fast with a tight impact zone: 3 frames with every club from the tee or the fairway, and just 1 from the rough, bunkers and other bad lies (wedges hold up best; putts aside) and **no auto swing**: on his power press only **B** works (A does nothing), and you time the impact yourself. Putts work as usual. He doesn't talk yet.
- **A new course: Pebble Beach.** All 18 holes laid out like the real Pebble Beach Golf Links on Carmel Bay, from map data: real fairway, green, bunker and tee shapes on the real ground, the cliffs and the sea along holes 4 to 10 and 17 and 18, trees, the houses round the course, The Lodge by the 1st tee and 18th green, and the hills round the bay on the horizon. On the course select screen it's the 8th course (right after Congo Canopy). Stroke Play, Match Play, Skins and Practice. The real holes are long, so every golfer hits 50 yards past their normal driver distance here (the other clubs in proportion); a Star version drives like its normal self on this course, and Tony, already the longest driver, keeps his 350.
- **Team Play: Best Ball, Scramble, Worst Ball and Wolf.** The Play Mode entry that was *Doubles* is now **Team Play**: its first five choices are the game's alternate-shot doubles, and six more games follow them:
  - **Best Ball Match** and **Best Ball Stroke** (2 vs 2): everyone plays their own ball, and on each hole a team counts its better player's score. Match: the better team score wins the hole, a tie halves it. Stroke: fewest total strokes. Once a teammate's score can't be beaten, the other picks up.
  - **Scramble** (2 vs 2): everyone on a team hits from the same spot, then the team's captain picks the ball the team plays next; each round of shots is one stroke, and whoever's ball the team takes hits first in the next round. The captain is the team's lowest-numbered player (1P, and 3P on the other team with the first team layout). The pick menu lists every ball with its distance to the pin and its lie, starting on the best one; moving between them flies the camera to that ball, and the C-stick turns round it (left/right) and zooms (up/down). A shot out of bounds or in the water only costs a stroke if the team takes it, and a ball in the hole is taken straight away.
  - **Worst Ball** (2 vs 2): like Scramble, everyone on a team hits from the same spot, but the team has to play its *worst* ball, picked for you: a ball that missed the hole before one that went in, then a ball out of bounds or in the water (with its penalty stroke), then the one farthest from the pin (a ball in the rough or a bunker counts as a bit farther). A team only holes out when everyone holes from the same spot.
  - **Team Scramble**: everyone who picked the game is one team (2, 3 or 4 players: pick 2, 3 or 4 Players on the main menu first), playing a scramble together; 1P picks the ball.
  - **Wolf** (3 or 4 players, no CPUs: pick 3 or 4 Players on the main menu first): everyone plays their own ball. Each hole has a Wolf, shown when the hole starts: the last player on hole 1, then 1P, 2P and so on in turn. The others tee off in order and the Wolf tees off last. Right after each player's drive the Wolf decides whether to **team up with them**; say no and the next player hits, and you can't go back for them. Turn down everyone and you're the **Lone Wolf**, playing alone against the rest. Each hole is a best-ball match, the Wolf's side against the others: each player on the winning side gets 1 point; a Lone Wolf who wins gets 2; when the Lone Wolf loses, each of the others gets 1. A tie gets nobody anything. The most points after the round wins. The points show on the score panel, the scoreboard after each hole and the results. Wolf's menu flies the camera to the ball just hit; the C-stick turns round it and zooms.

  Best Ball, Scramble and Worst Ball use the same team screen as alternate shot, and CPUs fill the empty seats (a team of CPUs takes the best shot in Scramble). Scramble, Worst Ball and Team Scramble play by stroke-play rules. Rules for Wolf as in [Golf Digest's guide](https://www.golfdigest.com/story/golf-game-wolf-betting-gambling-explained).
- **TV-style cameras:** after you hit, the camera cuts to behind and above the ball and follows it all the way. Putts are aimed, stroked and followed from behind the ball, down the line.
- **Power to the yard:** the left stick moves the landing spot and the power gauge in quarter steps (1 yard with a 240-yard driver; finer with shorter clubs) instead of 4-yard jumps. Putts keep the game's own steps.
- **See-through golfer when putting:** your golfer turns see-through from lining up the putt until the ball rolls, so the line, the grid and the cup stay in view. Turn it off and on with **Start → See-Through**; it's on every time the game starts.
- **Zoom view that shows where you're going:** it starts behind your ball looking down the line, and as you hold it the camera glides up and along the line until it's high behind your landing spot, always looking at the landing spot. Let go to stop partway; no more skimming the ground or ending up behind trees.
- **Clean yardage box:** the power bar's distance sits in a snug box with rounded corners, centred on the number, without the L/R button wings.
- **Hold RT (Right Trigger) to fast-forward** the ball after you hit (about 3× speed). The ball ends up exactly where it would have.
- **No intro movie** and no shattered-glass screen effect.
- **Replays ask first:** B after a shot opens *Continue / Watch Replay* instead of replaying straight away. Only the player who hit can open it.
- **Club Slots:** the item reel no longer has *Double the points*; its slots went to the other four items.
- **Separate entry:** shows up in Dolphin as *Mario Golf: Toadstool Tour (Mod vN)* with its own game ID (GFTEMD) and save, next to your normal copy.
- **Fullscreen and sharp:** starts fullscreen over the whole screen at a resolution that fits your screen, with HD UI textures by NickPancakes installed automatically. Click both sticks in (or Alt+Enter) to switch between fullscreen and a window; Esc no longer stops the game and drops you out of fullscreen (Shift+Esc stops it). These are Dolphin's hotkeys, so they apply in other games too; `Play.bat` only changes them if you haven't set your own.
- **Automatic updates:** `Play.bat` checks for a new version every time you start the game.

## Controls (any Xbox, PlayStation or Switch-style controller)

| Control | Does |
| --- | --- |
| Left stick left/right | Aim |
| Left stick up/down | Power: moves the landing spot farther/closer a yard at a time (and the power gauge with it); tilt further to move it faster |
| LB / RB | Change club |
| LT / RT | Switch views (RT looks down to the hole or landing spot); hold RT after the hit to fast-forward |
| Right stick | Turn the camera; up/down also sets the power |
| View / Back | Side view while held |
| A | Swing |
| Start | Pause menu (Scorecard, Rules, ..., **See-Through** on/off) |
| Click the left stick in | The game's L: on the character select screen, left-handed on/off |
| Click the right stick in | The game's R: on the character select screen, the Star version on/off |
| Click both sticks in | Fullscreen on/off (Alt+Enter on the keyboard does the same) |
| Shift+Esc | Stop the game (Esc alone does nothing, so it can't throw you out of fullscreen) |

Every way of looking around still works on putts: the camera goes back down the line when you let go. `Play.bat` sets these controls up for the modded game only, the same for whatever controller you plug in (buttons by position: Xbox A = PlayStation Cross = Switch B), whatever Dolphin's Port 1 says; other games keep your own settings. It sets them again every time it runs, so nothing in your own Dolphin settings can change them for the mod. They work on any Xbox-style controller slot (also when Steam or DS4Windows adds a virtual controller), on every controller your Dolphin has been set up with, and with a portable Dolphin. Port 1 is a Standard Controller for the mod (a GameCube controller adapter stays as it is). If Port 1 is your keyboard, or a controller whose buttons Dolphin only knows by number, its own buttons keep working too.

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

Up to 4 players. Everyone needs the latest mod version (run `Play.bat` or `Update only.bat` first), the same Dolphin version, and **Controllers → Port 1** set to *Standard Controller* (Dolphin's default; `Play.bat` sets up the buttons).

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
- **Cameras, fast-forward, no intro, yard-by-yard power, see-through golfer, Shy Guy's power shot:** written for this mod.
- **Shy Guy's model (v9 on):** his model and textures from *Mario Power Tennis* (Nintendo / Camelot). Changed for this mod: converted to this game's model format, fitted to Koopa Troopa's skeleton so he moves with Koopa's animations, and rendered for the menu pictures.
- **Shy Guy's model (v7-v8):** "[Shy Guy](https://sketchfab.com/3d-models/shy-guy-ed5356a5ee384034acc3145079d25fe4)" by Jakob Henerey, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changed for this mod: converted to the game's model format, fitted to Koopa Troopa's skeleton so he moves with Koopa's animations, made a little smaller with the arms moved onto Koopa's, and rendered for the menu pictures.
- **Tony the Tiger's model:** "[tony the tiger](https://sketchfab.com/3d-models/tony-the-tiger-6d538d698e1c4dafb1f9defbeaede572)" by J0RD4N, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changed for this mod: simplified, converted to the game's model format, fitted to Waluigi's skeleton (fingers included, so he holds the club) and smoothly skinned so he moves with Waluigi's animations, and rendered for the menu pictures. Tony the Tiger is Kellogg's character; this is a fan mod, not affiliated with Kellogg's.
- **Shy Guy's voice:** his clips from *Mario Power Tennis* (Nintendo / Camelot), ripped by RatchetMario for [The Sounds Resource](https://sounds.spriters-resource.com/gamecube/mariopowertennis/asset/395349/).
- **Pebble Beach course:** hole layouts, buildings, coastline and trees from [OpenStreetMap](https://www.openstreetmap.org/copyright) (© OpenStreetMap contributors, ODbL); elevation from the [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) open dataset (USGS 3DEP and others). The course is a fan recreation, not affiliated with Pebble Beach Company. Its grass, sand, sea, rock and tree models are the game's own (Cheep Cheep Falls and Blooper Bay); house and road textures were made for this mod.
- **HD UI textures:** "Toadstool Tour 4x" by NickPancakes ([Dolphin forum thread](https://forums.dolphin-emu.org/Thread-mario-golf-toadstool-tour-gcn-4x-ui-texture-pack)). Downloaded from the author's own link, not re-hosted here.

Please don't share game files (.iso and similar). Share this repo; everyone builds from their own copy.

## For the maintainer

`dev/` holds the tools that decode the game's files and build the mod; see [`dev/README.md`](dev/README.md). What's been learned about the game's code (addresses, structures, hooks) is in [`dev/RE-NOTES.md`](dev/RE-NOTES.md), and the live-testing tools are in `dev/tools/`. To publish version N, run `dev\publish.ps1`, then commit and push. Everyone's next `Play.bat` picks it up.
