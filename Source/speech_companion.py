"""Manual-only KCD2 log-to-speech proof. No game injection or startup registration."""
import sys
import base64
import configparser
import argparse
import json
import msvcrt
import re
import subprocess
import threading
import time
import queue
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
GAME_LOG = ROOT.parent.parent / 'kcd.log'
SPEECH_SETTINGS = json.loads((ROOT/'Build/reader-settings.json').read_text(encoding='utf-8'))
SPEECH_BACKEND = SPEECH_SETTINGS.get('speech_backend', 'piper')
if SPEECH_BACKEND != 'piper':
    raise ValueError('Unknown speech backend')
PIPER_PROFILES = {'cori': ('Piper Cori', 'PiperCori')}
PIPER_PROFILE = SPEECH_SETTINGS.get('piper_voice', 'cori')
if SPEECH_BACKEND == 'piper' and PIPER_PROFILE not in PIPER_PROFILES:
    raise ValueError('Unknown Piper voice profile')
VOICE = PIPER_PROFILES[PIPER_PROFILE][0] if SPEECH_BACKEND == 'piper' else 'Microsoft Ryan'
STOP_FILE = ROOT / 'Build' / 'stop-companion'

def read_piper_rate(path):
    """Reader-only INI; reload when starting speech, never mutate other voices."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with Path(path).open(encoding='utf-8-sig') as stream:
            parser.read_file(stream)
    except FileNotFoundError:
        return 0
    try:
        rate = parser.getint('Speech', 'PiperRate', fallback=0)
    except (ValueError, configparser.Error) as exc:
        raise ValueError('PiperRate must be an integer from -10 to 10') from exc
    if not -10 <= rate <= 10:
        raise ValueError('PiperRate must be an integer from -10 to 10')
    return rate


def clean(text):
    text = text.replace('</paragraph>', '\n\n').replace('</years>', '\n')
    text = re.sub(r'<[^>]*>', '', text)
    for old, new in [('&nbsp;', ' '), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"), ('&amp;', '&')]:
        text = text.replace(old, new)
    return text

def clean_book(text):
    # Preserve section boundaries without speaking formatting or page markers.
    text = re.sub(r'<newpage\s*/>', '\n\n', text)
    text = re.sub(r'</(?:title|heading|subtitle|li)>', '\n\n', text)
    return re.sub(r'[ \t]+', ' ', clean(text)).strip()

class WorkerHost:
    """Own only this reader's worker; reset its process for active book cancellation."""
    def __init__(self, report, null_audio=False, game_root=None):
        self.report, self.null_audio = report, null_audio
        self.game_root = Path(game_root) if game_root else GAME_LOG.parent
        self.events = queue.Queue()
        self.process = None
        self.start()

    def start(self):
        voice = base64.b64encode(VOICE.encode()).decode()
        if SPEECH_BACKEND == 'piper':
            package = self.game_root / 'Mods/codex_and_book_reader/Speech' / PIPER_PROFILES[PIPER_PROFILE][1]
            args = [str(package/'python/python.exe'), str(package/'piper_worker.py')]
        else:
            args = [str(ROOT/'Build/NaturalVoiceSpeechWorker.exe'), '--voice-base64', voice]
        if self.null_audio:
            args.append('--null-audio')
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.process = process
        ready = queue.Queue()
        def collect(owned):
            first = owned.stdout.readline().strip()
            self.report(first); ready.put(first)
            for line in owned.stdout:
                self.report('WORKER ' + line.strip())
                self.events.put(line.strip())
        threading.Thread(target=collect, args=(process,), daemon=True).start()
        try:
            if not ready.get(timeout=20).startswith('READY\t'):
                raise RuntimeError('Speech worker did not become ready')
        except Exception:
            self.close(); raise

    def send(self, line):
        if self.process.poll() is not None:
            raise RuntimeError('Speech worker exited')
        self.process.stdin.write(line + '\n'); self.process.stdin.flush()

    def reset(self, serial):
        if SPEECH_BACKEND == 'piper':
            # Router already sent STOP; keep the neural model loaded.
            self.report('BOOK CANCEL retained Piper worker serial=%d' % serial)
            return
        retired = self.process
        self.report('BOOK WORKER RESET begin serial=%d oldPid=%d' % (serial, retired.pid))
        if retired.poll() is None:
            retired.terminate()
            try:
                retired.wait(timeout=2)
            except subprocess.TimeoutExpired:
                retired.kill(); retired.wait(timeout=2)
        retired.stdin.close()
        self.start()
        self.report('BOOK WORKER RESET ready serial=%d newPid=%d' % (serial, self.process.pid))

    def close(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.stdin.write('QUIT\n'); process.stdin.flush(); process.stdin.close()
                process.wait(timeout=3)
            except Exception:
                process.kill(); process.wait(timeout=3)

class Router:
    def __init__(self, articles, send, report, books=None, reset_worker=None, rate_provider=None, feature_provider=None):
        self.articles, self.send, self.report = articles, send, report
        self.books = books or {}
        self.reset_worker = reset_worker
        self.piper_rate = 0
        self.feature_provider=feature_provider or (lambda: {"codex_enabled":1,"books_enabled":1})
        self.codex_enabled=self.books_enabled=True
        self.rate_provider = rate_provider or (lambda: read_piper_rate(GAME_LOG.parent / "Mods/codex_and_book_reader/reader.ini"))
        self.active_book = False
        self.book_paused = False
        self.codex_paused = False
        self.book_pending = None
        self.codex_pending = None
        self.last_book_key = None
        self.book_generation = self.book_read_generation = self.book_selected = None
        self.serial = 0
        self.generation = None
        self.read_generation = None
        self.selected = None
        self.active_serial = None
        self.last_key = None

    def refresh_features(self):
        values=self.feature_provider()
        codex=bool(values['codex_enabled']);books=bool(values['books_enabled'])
        if self.active_serial is not None and ((self.active_book and not books) or (not self.active_book and not codex)):
            self.stop()
        self.codex_enabled,self.books_enabled=codex,books
        if not codex:self.selected=None
        if not books:self.book_selected=None

    def stop(self):
        reset_book = self.active_book and self.active_serial is not None
        self.active_book = False
        self.book_paused = False
        self.codex_paused = False
        self.book_pending = None
        self.codex_pending = None
        self.last_book_key = None
        self.serial += 1
        self.send('STOP\t' + str(self.serial))
        self.book_generation = self.book_read_generation = self.book_selected = None
        self.active_serial = None
        self.selected = None
        if reset_book and self.reset_worker is not None:
            self.reset_worker(self.serial)

    def completed(self, line):
        ack = re.fullmatch(r'(PAUSED|RESUMED)	(\d+)', line)
        if ack:
            status, serial = ack.groups()
            expected = 'PAUSE' if status == 'PAUSED' else 'RESUME'
            if self.active_book and self.active_serial == int(serial) and self.book_pending == (expected, int(serial)):
                self.book_paused = status == 'PAUSED'
                self.book_pending = None
                self.codex_pending = None
                self.report('BOOK ' + status + ' serial=' + serial)
            elif not self.active_book and self.active_serial == int(serial) and self.codex_pending == (expected, int(serial)):
                self.codex_paused = status == 'PAUSED'
                self.codex_pending = None
                self.report('CODEX ' + status + ' serial=' + serial)
            return
        parts = line.split('\t')
        if len(parts) >= 3 and parts[0] == 'DONE' and parts[1] == str(self.active_serial):
            self.active_serial = None
            self.active_book = False
            self.book_paused = False
            self.codex_paused = False
            self.book_pending = None
            self.codex_pending = None

    def toggle(self):
        if self.selected is None:
            return
        if self.codex_pending is not None:
            self.report('CODEX Play/Pause ignored: awaiting worker confirmation')
            return
        if self.active_serial is None:
            self.speak(self.selected)
            self.report('TOGGLE READ')
        elif not self.active_book:
            command = 'RESUME' if self.codex_paused else 'PAUSE'
            self.codex_pending = (command, self.active_serial)
            self.send(command + '\t' + str(self.active_serial))
            self.report('CODEX ' + command + ' requested serial=' + str(self.active_serial))

    def toggle_book(self):
        if self.book_selected not in self.books:
            return
        if self.book_pending is not None:
            self.report('BOOK Play/Pause ignored: awaiting worker confirmation')
            return
        if self.active_serial is None:
            self.speak(self.book_selected, book=True)
        elif self.active_book:
            command = 'RESUME' if self.book_paused else 'PAUSE'
            self.book_pending = (command, self.active_serial)
            self.send(command + '\t' + str(self.active_serial))
            self.report('BOOK ' + command + ' requested serial=' + str(self.active_serial))

    def speak(self, entry, book=False):
        self.refresh_features()
        if (book and not self.books_enabled) or (not book and not self.codex_enabled):
            self.report("REFUSED disabled reading feature");return
        article = (self.books if book else self.articles).get(entry)
        if not article:
            self.report('REFUSED unknown entry'); return
        text = clean_book(article['body']) if book else article['title'] + '.\n\n' + clean(article['body'])
        if not text.strip() or len(text) > 19000:
            self.report('REFUSED length'); return
        self.serial += 1
        payload = base64.b64encode(text.encode('utf-8')).decode('ascii')
        rate = 1  # Preserve the existing local Ryan/SAPI rate.
        if SPEECH_BACKEND == 'piper':
            try:
                candidate = self.rate_provider()
                if type(candidate) is not int or not -10 <= candidate <= 10:
                    raise ValueError('PiperRate must be an integer from -10 to 10')
                self.piper_rate = candidate
            except (ValueError, OSError, UnicodeError, configparser.Error) as exc:
                self.report('PIPER RATE settings invalid; retaining step=%d: %s' % (self.piper_rate, exc))
            rate = self.piper_rate
            self.report('PIPER RATE step=%d' % rate)
        self.send('SPEAK\t%d\t90\t%d\t%s' % (self.serial, rate, payload))
        self.active_serial = self.serial
        self.active_book = book
        self.book_paused = False
        self.codex_paused = False
        self.book_pending = None
        self.codex_pending = None
        self.report(('BOOK REQUEST' if book else 'REQUEST') + ' serial=%d title=%s chars=%d' % (self.serial, article['title'], len(text)))

    def line(self, line):
        self.refresh_features()
        if '[CodexProbe] v' in line and 'loaded;' in line:
            self.stop(); self.generation = self.read_generation = self.last_key = None
        book_key = re.search(r'\[BookSpeech\] TOGGLE (\d+) (\d+) ([0-9a-z-]{36})\s*$', line)
        if book_key:
            generation, serial, entry = book_key.groups()
            identity = (int(generation), int(serial))
            if int(generation) == self.book_generation and entry == self.book_selected and entry in self.books and identity != self.last_book_key:
                self.last_book_key = identity
                self.toggle_book()
            else:
                self.report('REFUSED stale, duplicate or unselected book Play/Pause')
            return
        book_state = re.search(r'\[BookSpeech\] STATE (\d+) OPEN ([0-9a-z-]{36})\s*$', line)
        if book_state:
            generation, entry = book_state.groups()
            self.book_selected = entry if int(generation) == self.book_generation and entry in self.books else None
            return
        book_command = re.search(r'\[BookSpeech\] (STOP|READ) (\d+)(?: ([0-9a-z-]{36}))?\s*$', line)
        if book_command:
            command, generation, entry = book_command.groups()
            generation = int(generation)
            if command == 'STOP':
                self.stop()
                self.generation = self.read_generation = self.last_key = None
                self.book_generation = generation
                self.report('BOOK CANCEL gameGeneration=' + str(generation))
            elif generation != self.book_generation or generation == self.book_read_generation or entry != self.book_selected or entry not in self.books:
                self.report('REFUSED stale, duplicate or unselected book request')
            else:
                self.speak(entry, book=True)
                self.book_read_generation = generation
            return
        key = re.search(r'\[CodexSpeech\] KEYTOGGLE (\d+) (\d+) ([0-9a-f-]{36})\s*$', line)
        if key:
            generation, serial, entry = key.groups()
            identity = (int(generation), int(serial))
            if int(generation) == self.generation and entry == self.selected and identity != self.last_key:
                self.last_key = identity
                self.report('KEYBOARD Play/Pause received')
                self.toggle()
            else:
                self.report('REFUSED stale, duplicate or unselected keyboard request')
            return
        state = re.search(r'\[CodexSpeech\] STATE (\d+) (OPEN|CLOSED)(?: ([0-9a-f-]{36}))?\s*$', line)
        if state:
            generation, status, entry = state.groups()
            self.selected = entry if status == 'OPEN' and int(generation) == self.generation and entry in self.articles else None
            return
        match = re.search(r'\[CodexSpeech\] (STOP|READ) (\d+)(?: ([0-9a-f-]{36}))?\s*$', line)
        if not match:
            return
        command, generation, entry = match.groups()
        generation = int(generation)
        if command == 'STOP':
            self.stop(); self.generation = generation; self.read_generation = None
            self.report('CANCEL gameGeneration=' + str(generation))
            return
        # Every READ must follow its own STOP. No startup replay or duplicated request.
        if generation != self.generation or generation == self.read_generation:
            self.report('REFUSED stale or duplicate request'); return
        self.speak(entry)
        self.selected = entry if entry in self.articles else None
        self.read_generation = generation

def main(argv=None):
    parser = argparse.ArgumentParser(description='KCD2 manual-on-demand speech helper')
    parser.add_argument('--game-pid', type=int)
    parser.add_argument('--game-log', type=Path)
    options = parser.parse_args(argv)
    game_log = options.game_log if options.game_log is not None else GAME_LOG
    if not game_log.is_absolute():
        raise ValueError('Game log path must be absolute')
    # Hold an OS lock for process lifetime, avoiding duplicate companions.
    lock = open(ROOT / 'Build' / 'companion.lock', 'a+b')
    if lock.seek(0, 2) == 0:
        lock.write(b'0'); lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return
    # A newly owning helper may clear a previous session's stop flag.
    STOP_FILE.unlink(missing_ok=True)
    report_lock = threading.Lock()
    output = open(ROOT / 'Build' / 'speech-companion.log', 'a', encoding='utf-8', buffering=1)
    def report(message):
        with report_lock:
            output.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + message + '\n')
    host = None
    lifetime = None
    mcm_bridge = None
    try:
        if options.game_pid is not None:
            from game_lifetime import GameLifetime
            lifetime = GameLifetime(options.game_pid)
            if not lifetime.alive():
                report('GAME PROCESS ALREADY EXITED'); return
        host = WorkerHost(report, game_root=game_log.parent)
        if lifetime is not None and not lifetime.alive():
            report('GAME PROCESS EXITED DURING STARTUP'); return
        worker_events = host.events
        send = host.send
        articles = json.loads((ROOT/'Build/english_articles.json').read_text(encoding='utf-8'))
        books = json.loads((ROOT/'Build/book_english_text.json').read_text(encoding='utf-8'))
        router = Router(articles, send, report, books=books, reset_worker=host.reset,
                        rate_provider=lambda: read_piper_rate(game_log.parent / "Mods/codex_and_book_reader/reader.ini"),
                        feature_provider=lambda: mcm_bridge.options)
        controller = None
        from controller_input import Controller, Hold
        hold = Hold()
        settings = json.loads((ROOT/'Build/reader-settings.json').read_text(encoding='utf-8'))
        if settings.get('controller_hold_y', False):
            try:
                controller = Controller()
                report('CONTROLLER hold Y 0.8s toggle enabled; foreground Codex only')
            except Exception as exc:
                report('CONTROLLER unavailable: ' + type(exc).__name__ + '; console commands retained')
        # Begin at EOF of any old log. Only subsequent commands can speak.
        position = game_log.stat().st_size if game_log.exists() else 0
        pending = b''
        from reader_mcm import SettingsBridge
        mcm_bridge = SettingsBridge(game_log.parent, report, read_piper_rate, piper=SPEECH_BACKEND == 'piper')
        report('ARMED voice=' + VOICE + ' oldLogSkipped=true')
        (ROOT/'Build/companion-ready.json').write_text(json.dumps({'pid':os.getpid(), 'state':'armed', 'voice':VOICE, 'game_pid':options.game_pid, 'worker_pid':host.process.pid}), encoding='utf-8')
        diagnostic_last = None
        diagnostic_count = 0
        while not STOP_FILE.exists():
            if lifetime is not None and not lifetime.alive():
                router.stop(); report('GAME PROCESS EXITED'); return
            if host.process.poll() is not None:
                raise RuntimeError('Speech worker exited')
            mcm_bridge.refresh()
            router.refresh_features()
            while not worker_events.empty():
                router.completed(worker_events.get_nowait())
            if game_log.exists():
                size = game_log.stat().st_size
                if size < position:
                    router.stop(); router.generation = router.read_generation = None
                    position = 0; pending = b''; report('LOG RESET')
                with game_log.open('rb') as stream:
                    stream.seek(position)
                    block = stream.read(262144)
                    position = stream.tell()
                pending += block
                pieces = pending.split(b'\n'); pending = pieces.pop()
                if len(pending) > 65536:
                    pending = b''; router.stop(); report('REFUSED oversized log line')
                for raw in pieces:
                    line = raw.decode('utf-8', errors='replace').rstrip('\r')
                    if not mcm_bridge.handle_line(line):
                        router.line(line)
                    else:
                        router.refresh_features()
                    if 'CSystem::Quit invoked' in line:
                        router.stop(); report('GAME QUIT'); return
            if controller is not None:
                foreground = controller.foreground_game()
                if not foreground and router.active_serial is not None:
                    selected = router.selected
                    router.stop(); router.selected = selected
                    report('FOCUS LOST: stopped speech')
                eligible = foreground and router.selected is not None
                slots, pressed = controller.snapshot() if eligible else (None, False)
                diagnostic_state = (foreground, router.selected is not None, slots, pressed)
                if settings.get('input_diagnostics', False) and diagnostic_state != diagnostic_last and diagnostic_count < 80:
                    report('INPUT foreground=%s articleSelected=%s xinputSlots=%s Y=%s' % diagnostic_state)
                    diagnostic_count += 1
                diagnostic_last = diagnostic_state
                if hold.update(eligible and pressed, time.monotonic()):
                    report('INPUT HOLD reached')
                    router.toggle()
            time.sleep(0.1)
    except Exception as exc:
        report('ERROR ' + type(exc).__name__ + ': ' + str(exc))
    finally:
        if mcm_bridge is not None:
            mcm_bridge.close()
        if host is not None:
            host.close()
        if lifetime is not None:
            lifetime.close()
        report('EXIT')
        ready_file = ROOT/'Build/companion-ready.json'
        if ready_file.exists():
            ready_file.unlink()
        output.close(); lock.close()

if __name__ == '__main__':
    main()
