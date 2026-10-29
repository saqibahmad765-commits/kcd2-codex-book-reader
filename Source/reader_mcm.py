"""Optional MCM/INI controls for the reader; no shared speech or game settings."""
import configparser
import os
from pathlib import Path
import re
import secrets
import time

KEYS = ('none','pause','scrolllock','home','end','insert','delete','pgup','pgdn',
        'f1','f2','f3','f4','f5','f6','f7','f8','f9','f10','f11','f12')
FIELDS = {
 'piper_rate': ('Speech','PiperRate',0),
 'codex_enabled': ('Speech','CodexEnabled',1),
 'books_enabled': ('Speech','BooksEnabled',1),
 'play_key': ('Keys','PlayPause',1),
 'restart_key': ('Keys','Restart',2),
}

def validate_options(values):
    if set(values) != set(FIELDS):raise ValueError('Incomplete reader settings')
    for key,value in values.items():
        if type(value) is not int:raise ValueError(key+' must be an integer')
        if key=='piper_rate':valid=-10<=value<=10
        elif key.endswith('_enabled'):valid=value in (0,1)
        else:valid=0<=value<len(KEYS)
        if not valid:raise ValueError('Invalid reader setting: '+key)
    if values['play_key'] and values['play_key']==values['restart_key']:
        raise ValueError('Play/pause and restart must use different keys (or Unbound)')
    return values

def read_options(path):
    parser=configparser.ConfigParser(interpolation=None)
    try:
        with Path(path).open(encoding='utf-8-sig') as stream:parser.read_file(stream)
    except FileNotFoundError:pass
    values={}
    for field,(section,key,default) in FIELDS.items():
        if section=='Keys':
            value=parser.get(section,key,fallback=KEYS[default]).strip().lower()
            if value not in KEYS:raise ValueError('Unsupported reader key: '+value)
            values[field]=KEYS.index(value)
        else:values[field]=parser.getint(section,key,fallback=default)
    return validate_options(values)

class SettingsBridge:
    pattern = re.compile(r'\[CodexReaderSettings\] SET_RATE ([0-9a-f]{16}) ([0-9]{1,9}) (-?[0-9]{1,2})\s*$')
    option_pattern = re.compile(r'\[CodexReaderSettings\] SET_OPTION ([0-9a-f]{16}) ([0-9]{1,9}) ([a-z_]{1,24}) (-?[0-9]{1,2})\s*$')
    def __init__(self, game_root, report, read_rate=None, piper=True):
        self.root=Path(game_root)/'Mods/codex_and_book_reader'
        self.ini=self.root/'reader.ini';self.state=self.root/'reader-mcm-state.cfg'
        self.report,self.read_rate,self.piper=report,read_rate,piper
        self.token=secrets.token_hex(8);self.sequence=0;self.ok=True
        self.options={key:spec[2] for key,spec in FIELDS.items()};self.rate=0
        self.next_poll,self.last_blob,self.last_error=0.0,None,None
        self.refresh(force=True)

    @staticmethod
    def atomic_write(path,content):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
        try:
            with temp.open('w',encoding='utf-8',newline='\n') as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        finally:temp.unlink(missing_ok=True)

    def publish(self,ready=True):
        o=self.options
        blob=('-- Generated reader state; do not edit.\n'
              'cdx_mcm_state %s %d %d %d %d %d %d %d %d\n'
              % (self.token,self.sequence,self.rate,int(ready),int(self.ok),o['codex_enabled'],o['books_enabled'],o['play_key'],o['restart_key']))
        if blob==self.last_blob:return
        try:self.atomic_write(self.state,blob);self.last_blob=blob
        except OSError as exc:self.report('MCM STATE unavailable: '+str(exc))

    def refresh(self,force=False):
        now=time.monotonic()
        if not force and now<self.next_poll:return
        self.next_poll=now+1.0
        try:
            self.options=read_options(self.ini);self.rate=self.options['piper_rate'];self.last_error=None
        except (ValueError,OSError,UnicodeError,configparser.Error) as exc:
            if str(exc)!=self.last_error:
                self.report('MCM INI invalid; retaining last valid settings: '+str(exc));self.last_error=str(exc)
        self.publish()

    def persist(self,rate):self.persist_option('piper_rate',rate)

    def persist_option(self,field,value):
        if field not in FIELDS:raise ValueError('Unknown reader setting')
        proposed=read_options(self.ini).copy();proposed[field]=value;validate_options(proposed)
        section,key,_=FIELDS[field];text=KEYS[value] if section=='Keys' else str(value)
        try:old=self.ini.read_text(encoding='utf-8-sig')
        except FileNotFoundError:old=''
        parser=configparser.ConfigParser(interpolation=None);parser.read_string(old)
        lines=old.splitlines(keepends=True);current=None;found=False
        for index,line in enumerate(lines):
            header=re.match(r'\s*\[([^]]+)\]',line)
            if header:
                if current==section:
                    lines.insert(index,key+'='+text+'\n');found=True;break
                current=header.group(1)
            if current==section and re.match(r'\s*'+re.escape(key)+r'\s*[=:]',line,re.I):
                prefix=re.match(r'(\s*'+re.escape(key)+r'\s*[=:]\s*)',line,re.I).group(1)
                lines[index]=prefix+text+'\n';found=True;break
        if not found:
            suffix='' if not lines or lines[-1].endswith(('\n','\r')) else '\n'
            if current!=section:suffix+='['+section+']\n'
            lines.append(suffix+key+'='+text+'\n')
        content=''.join(lines)
        if old:self.atomic_write(self.ini.with_name('reader.previous.ini'),old)
        self.atomic_write(self.ini,content)
        try:
            actual=read_options(self.ini)
            if actual!=proposed:raise ValueError('Saved settings verification failed')
        except Exception:
            self.atomic_write(self.ini,old);raise
        self.options=actual;self.rate=actual['piper_rate']

    def handle_line(self,line):
        match=self.pattern.search(line)
        if match:
            token,sequence,value=match.groups();field='piper_rate'
        else:
            match=self.option_pattern.search(line)
            if not match:return False
            token,sequence,field,value=match.groups()
        sequence,value=int(sequence),int(value)
        if token!=self.token or sequence<=self.sequence or sequence<1:
            self.report('MCM REFUSED stale/session-mismatched request');return True
        self.sequence=sequence
        try:
            if field=='piper_rate':self.persist(value)
            else:self.persist_option(field,value)
            self.ok=True;self.report('MCM SAVED %s=%d request=%d'%(field,value,sequence))
        except (ValueError,OSError,UnicodeError,configparser.Error) as exc:
            self.ok=False;self.report('MCM SAVE FAILED: '+str(exc))
        self.publish();return True

    def close(self):self.publish(ready=False)
