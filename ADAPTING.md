# Community adaptations

Original reader code is GPL-3.0-or-later. Preserve third-party licences and credits.
Modified distributions must meet applicable source/notices requirements. Contributors
may make their own adaptations; the original author does not promise maintenance
or support for additional voices/languages.

For a compatible single-speaker Piper voice, place its ONNX model and matching
ONNX JSON configuration in Speech/PiperCori/voices, then edit voice-config.json's
model path. Keep it inside voices. The folder name is retained for compatibility;
the worker loads the configured model rather than a hard-coded model filename.
The displayed runtime diagnostic label remains Cori in this first release; adapters
should update it. Audit the new voice's licence separately. Existing Cori permissions
do not apply automatically to other models. Do not bundle Windows/NaturalVoice voices.

A new language also needs local game-text extraction for that language, correct
localisation precedence, text handling and voice matching. setup_reader.py currently
deliberately accepts only English. Change and test that guard in your fork rather
than promising multilingual support by replacing the model alone. No translation
engine or model-training platform is included.

Build with Python 3.12+, a Windows Zig compiler and the pinned prepared Cori package:
python build_portable.py --voice-package <prepared-folder> --compiler <zig.exe>
The validated compiler for this candidate is Zig 0.13.0. The compiler is a maintainer
tool, not an end-user dependency. prepare_cori.py and cori-package-lock.json reproduce
the runtime from pinned official downloads. Build into a fresh directory.

Keep generated game text, logs, settings, caches and private paths OUT of public
source and binary archives. Source/ contains authored code; UpstreamSource/ carries
Piper/eSpeak corresponding sources and provenance. Read its manifest for versions.
Retain all included source build files, licences and dependency notices.
