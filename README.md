# Codex and Book Reader

KCD2 offline book and Codex narration using Cori, a British female voice.

By **Squibster99**, with assistance from **Codex by OpenAI**.

This repository publishes the original source for **0.5.0-beta1**, for review and adaptation. It is not a ready-to-install mod download.

- [Build instructions](BUILDING.txt)
- [Usage and limitations](README.txt)
- [Voice and language adaptations](ADAPTING.md)
- [GPL licence](COPYING) and [third-party notices](THIRD-PARTY-NOTICES.md)
- [Matching upstream sources](UpstreamSource/README.md)

The startup DLL source is `Source/Startup/reader_startup.c`; Python helper and Lua integration sources are in `Source/`. The build prepares pinned dependencies and compiles the launcher using Zig 0.13.0. Upstream binaries are not rebuilt by that launcher build.

No game text, voice model, compiled runtime, personal settings or diagnostic logs are published here. Setup extracts required text locally from the player's own installation. Third-party components retain their separate licences.

## Release identification

Original main archive SHA-256: `f755d671674dd99424e32310e451c023fcfedc3a9c43d6da2013685ba215e14c`.

The publication of source does not imply Nexus quarantine clearance or a new gameplay-tested build. Current repository documents differ from the archived source only to explain this GitHub layout.
