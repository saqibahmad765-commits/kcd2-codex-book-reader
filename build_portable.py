"""Build a clean release candidate; no deployment and no extracted game text."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, zipfile
ROOT=Path(__file__).resolve().parent

def build(voice,compiler):
    package=ROOT/'Build/Package/Mods/codex_and_book_reader'
    if (package/'Build/catalogue-ready.json').exists():raise RuntimeError('Refusing to package a configured installation containing game text')
    for folder in ('Source','Build','Data','KCSE/Plugins','Speech/PiperCori','Licenses'):
        (package/folder).mkdir(parents=True,exist_ok=True)
    for name in ('speech_companion.py','reader_mcm.py','controller_input.py','game_lifetime.py','setup_reader.py'):
        shutil.copy2(ROOT/'Source'/name,package/'Source'/name)
    for name in ('reader.ini','Setup Reader.cmd'):shutil.copy2(ROOT/'Source'/name,package/name)
    with zipfile.ZipFile(package/'Data/codex_and_book_reader.pak','w',compression=zipfile.ZIP_STORED) as z:
        for name in ('codex_and_book_reader.lua','book_probe.lua','reader_mcm.lua'):
            z.write(ROOT/'Source'/name,'Scripts/Mods/'+name)
    (package/'mod.manifest').write_text('''<kcd_mod><info><name>Codex and Book Reader</name><modid>codex_and_book_reader</modid><description>Offline English Cori narration for Codex and base-game books. Run Setup Reader.cmd before first use.</description><author>Squibster99</author><version>0.5.0-beta1</version><created_on>2026-10-23</created_on></info><supports><version>1.5.6*</version></supports></kcd_mod>''',encoding='utf8')
    (package/'Build/reader-settings.json').write_text(json.dumps({'controller_hold_y':False,'input_diagnostics':False,'speech_backend':'piper','piper_voice':'cori'}))
    (package/'reader-mcm-state.cfg').write_text('; Helper publishes current session state here.\n')
    (package/'KCSE/Plugins/KCD2ReaderStartup.ini').write_text('[Reader]\nEnabled=1\n')
    for name in ('python','voices','licenses'):
        shutil.copytree(voice/name,package/'Speech/PiperCori'/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(ROOT/'Source/piper_worker.py',package/'Speech/PiperCori/piper_worker.py')
    (package/'Speech/PiperCori/voice-config.json').write_text(json.dumps({'name':'Cori','language':'en_GB','model':'voices/en_GB-cori-high.onnx'},indent=2))
    cache=ROOT/'Build/compiler-cache';cache.mkdir(exist_ok=True)
    env=os.environ.copy();env.update(ZIG_GLOBAL_CACHE_DIR=str(cache),ZIG_LOCAL_CACHE_DIR=str(cache/'local'),TMP=str(cache),TEMP=str(cache))
    output=package/'KCSE/Plugins/KCD2ReaderStartup.dll'
    cmd=[str(compiler),'cc','-target','x86_64-windows-gnu','-std=c11','-O2','-shared','-s',str(ROOT/'Source/Startup/reader_startup.c'),'-o',str(output)]
    subprocess.run(cmd,env=env,check=True)
    subprocess.run([str(compiler),'cc','-target','x86_64-windows-gnu','-std=c11','-O2','-municode',str(ROOT/'Tests/fixtures/startup_fixture.c'),'-o',str(ROOT/'Build/StartupTestHost.exe')],env=env,check=True)
    for name in ('README.txt','ADAPTING.md','THIRD-PARTY-NOTICES.md','COPYING','SOURCE-AVAILABILITY.txt'):
        shutil.copy2(ROOT/name,package/name)
    hashes={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.rglob('*')) if p.is_file()}
    (ROOT/'Build/payload-sha256.json').write_text(json.dumps(hashes,indent=2))
    print('Candidate built:',package)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--voice-package',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args();build(a.voice_package,a.compiler)
