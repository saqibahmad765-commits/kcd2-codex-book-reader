Codex and Book Reader - 0.5.0-beta1 (public beta)

Reads supported English Codex entries and base-game books aloud using Cori,
a British female voice. Speech is generated locally on your CPU. No account,
paid speech service, installed system voice or separate Python install is needed.

Requirements: Windows 64-bit, KCD2 Steam 1.5.6 (current test target), KCSE.
MCM is optional for in-game settings; follow MCM's own dependency instructions.
Other storefronts/game versions have not been tested. No loader is bundled.

INSTALL / SET UP
Close the game. Extract the supplied Mods folder into the game directory.
The result must be Mods/codex_and_book_reader/mod.manifest. If you use mod_order.txt,
add codex_and_book_reader once. Keep existing mods and load order intact.
Double-click Setup Reader.cmd inside the reader folder. Wait for its Ready message,
then start the game normally. Setup reads installed English game text and creates
a private local catalogue. No game text or pre-recorded narration is in this download.
Run setup again with the game closed after relevant game/localisation/mod changes.
Do not redistribute the locally generated catalogue or a configured installation.

USE
Open a Codex entry or supported book; press Pause/Break to play, pause or resume.
Scroll Lock restarts. Selection/close events cancel reading; occasional missed
screen events may require closing and reopening the screen. Book reading uses
the whole document, not the current visible page. No sentence skipping is provided.
MCM -> Codex and Book Reader: switch Codex/books independently, change speed,
or choose keyboard shortcuts. Reopen the screen after enabling a feature.
Speed changes affect new/restarted narration. Existing paused audio keeps its speed.

Defaults: both features on, speed 0, Pause/Break and Scroll Lock.
Without MCM, edit reader.ini with the game closed. [Speech]: CodexEnabled and
BooksEnabled are 0/1; PiperRate is -10..10. [Keys]: PlayPause and Restart support
none, pause, scrolllock, home, end, insert, delete, pgup, pgdn and f1..f12.
Choose different keys. These bindings can replace other game/mod bindings.

WITH AUDIO BOOK BY UNIWARS
Limited personal testing suggests coexistence. Recommended: our Codex on, our
books off, and separate shortcuts. F2/F3/F4 are Audio Book's defaults; F3/F4 also
overlap some camera mods. Both book readers enabled may introduce extra delay.
This is not a guarantee of compatibility across installations.

SCOPE / LIMITATIONS
English only. Base-game text-bearing documents only; no cooking-mod or other added
books. Setup applies installed English localisation replacements for known entries,
using mod_order.txt when present. Mod-added/rewritten item tables are not supported.
Without explicit load order, only simple folder-order localisation merging is used;
complex mod priorities need testing. This is not a general screen reader.
Cori is synthetic speech: cadence and foreign-name pronunciation can be imperfect.
CPU/RAM use and startup delay vary. The model is kept loaded while the helper runs.
Game text catalogue and speech controls work offline. No telemetry is added.

UPDATING / REMOVAL
Close the game first. Keep reader.ini to preserve your settings. Do not copy the
author's personal settings. Replace supplied files, then rerun setup. Users of private development builds should remove their old reader folder after
backing up reader.ini, install this clean package, restore that INI and rerun setup.
To remove, close the game, remove codex_and_book_reader from mod_order.txt if present,
and remove only Mods/codex_and_book_reader. Other mods/loaders are independent.
Keep a copy of reader.ini if wanted. No game saves are deliberately modified.

IF IT DOES NOT SPEAK
Confirm setup completed and the relevant feature is enabled. Reopen the screen.
Check KCSE and mod activation. Diagnostic files are KCSE/Plugins/KCD2ReaderStartup.log
and Build/speech-companion.log. Do not share your entire game log by default; share
the relevant reader lines, game/mod version, enabled features and exact steps.

KNOWN BETA ISSUE
Occasionally Codex narration stops after the title. Press Read (Pause/Break by
default) again to resume. If nothing starts, close and reopen the entry.
A single test suggested an interaction with the experimental Henry's Diary mod;
this is not a confirmed cause. Leave that prototype disabled when troubleshooting.

CREDITS AND SOURCE
By Squibster99, with assistance from Codex by OpenAI.
https://www.nexusmods.com/profile/Squibster99?gameId=1995
Original code: GPL-3.0-or-later, without warranty. Voice/runtime/dependency licences
are separate: see COPYING and THIRD-PARTY-NOTICES.md. Source and adaptation guide:
download Codex-and-Book-Reader-0.5.0-beta1-source.7z from this mod's Nexus Files tab.
See ADAPTING.md for community voice/language adaptations and their limitations.

Folder-name update: if you installed the earlier package, close the game and back up reader.ini. Remove the old Mods/codex_capture_probe folder and its mod_order.txt entry before installing this package. Restore your INI in Mods/codex_and_book_reader and rerun Setup Reader.cmd. Do not keep both folders installed. The new mod_order.txt entry is codex_and_book_reader (without quotes).

Correction: the folder, manifest ID and mod_order.txt entry must all be codex_and_book_reader. The displayed name remains Codex and Book Reader. Remove either earlier reader folder (codex_capture_probe or Codex and Book Reader) and replace its load-order entry; keep your reader.ini and rerun setup. Never keep two copies active.
