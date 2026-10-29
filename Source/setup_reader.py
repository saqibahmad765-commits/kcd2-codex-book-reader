"""Generate private catalogues from the user's installation; never distribute output."""
from pathlib import Path
import argparse, ctypes, hashlib, json, os, tempfile, zipfile
import xml.etree.ElementTree as ET

MOD_ID = 'codex_and_book_reader'
LOCAL_FILES = ('codex_record_index.lua','codex_english_text.lua','book_item_index.lua','book_text_snapshot.lua')

def parse(raw):
    try: return ET.fromstring(raw.decode('utf-8-sig'))
    except UnicodeDecodeError: return ET.fromstring(raw.decode('cp1252'))

def quote(value):
    # Lua 5.1 has no JSON \u escape. Preserve UTF-8 and escape control bytes explicitly.
    return '"'+''.join(('\\%03d'%ord(c)) if ord(c)<32 else '\\'+c if c in '\\"' else c for c in value)+'"'

def game_running():
    from ctypes import wintypes
    class ENTRY(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
          ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
          ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    k.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ENTRY)]
    k.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ENTRY)]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    h=k.CreateToolhelp32Snapshot(2,0)
    if h==ctypes.c_void_p(-1).value: raise OSError('Cannot check whether the game is running')
    try:
        entry=ENTRY();entry.dwSize=ctypes.sizeof(entry)
        found=k.Process32FirstW(h,ctypes.byref(entry))
        while found:
            if entry.szExeFile.lower()=='kingdomcome.exe':return True
            found=k.Process32NextW(h,ctypes.byref(entry))
        return False
    finally:k.CloseHandle(h)

def collect(game, language='English'):
    if language != 'English':raise ValueError('This release supports English only; localisation adapters must be tested separately')
    tables=game/'Data/Tables.pak';localisation=game/'Localization/English_xml.pak'
    with zipfile.ZipFile(tables) as z:
        perks={n.get('perk_id'):n for n in parse(z.read('Libs/Tables/rpg/perk.xml')).iter('perk')}
        codex=list(parse(z.read('Libs/Tables/rpg/perk_codex.xml')).iter('perk_codex'))
        docs=list(parse(z.read('Libs/Tables/item/item.xml')).iter('Document'))
    records={};keys=set()
    for node in codex:
        identifier=node.get('perk_id');perk=perks.get(identifier)
        if perk is None:raise ValueError('Codex references a missing perk')
        title=perk.get('perk_ui_name');body=node.get('codex_ui_text')
        if not title or not body:raise ValueError('Codex has incomplete text references')
        for alias in (identifier,perk.get('perk_name')):
            if alias:records[alias]={'title':title,'body':body}
        keys.update((title,body))
    books={}
    for node in docs:
        content=node.find('DocumentContent')
        if content is None or not content.get('Parts','').strip():continue
        identifier=node.get('Id');title=node.get('UIName');parts=content.get('Parts').split()
        if not identifier or not title:raise ValueError('Book has incomplete identity')
        books[identifier]={'titleKey':title,'name':node.get('Name',''),'parts':parts}
        keys.update([title,*parts])
    strings={};inputs=[]
    def load(path):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.lower().endswith('.xml'):continue
                raw=z.read(name)
                # Limit parsing to XML containing relevant keys; no archive extraction.
                if not any(k.encode('ascii') in raw for k in keys):continue
                tree=parse(raw)
                for row in tree.iter('Row'):
                    cells=row.findall('Cell')
                    if len(cells)>=3 and cells[0].text in keys:
                        strings[cells[0].text]=''.join(cells[2].itertext())
        inputs.append({'path':str(path.relative_to(game)),'size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns})
    load(localisation)
    # Respect English replacements for known base-game entries, not added documents.
    order=game/'Mods/mod_order.txt'
    if order.exists():
        mods=[s.strip() for s in order.read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#')]
    else:
        mods=sorted(p.name for p in (game/'Mods').iterdir() if p.is_dir())
    for mod in mods:
        if mod==MOD_ID:continue
        if '/' in mod or '\\' in mod or mod in ('.','..'):raise ValueError('Invalid mod-order entry')
        folder=game/'Mods'/mod/'Localization'
        if folder.exists():
            for path in sorted(folder.glob('*.pak')):
                if path.name.lower()=='english_xml.pak':load(path)
    missing=sorted(k for k in keys if not strings.get(k))
    if missing:raise ValueError('Missing English text keys: '+', '.join(missing[:12]))
    articles={k:{'title':strings[v['title']],'body':strings[v['body']]} for k,v in records.items()}
    speech_books={k:{'title':strings[v['titleKey']],'body':'\n\n'.join(strings[p] for p in v['parts'])} for k,v in books.items()}
    index='KCD2CodexRecordIndex={\n'+''.join('['+quote(k)+']={title='+quote(v['title'])+',body='+quote(v['body'])+'},\n' for k,v in sorted(records.items()))+'}\n'
    text='KCD2CodexEnglishText={\n'+''.join('['+quote(k)+']='+quote(v)+',\n' for k,v in sorted(strings.items()))+'}\n'
    book_index='KCD2BookItemIndex={}\nKCD2BookClassIndex={\n'
    book_text='KCD2BookPreviewIndex={\n'
    for identifier,b in sorted(books.items()):
        fields={'id':identifier,'titleKey':b['titleKey'],'name':b['name'],'title':strings[b['titleKey']],'parts':' '.join(b['parts']),'source':'local installation'}
        book_index+='['+quote(identifier)+']={'+','.join(k+'='+quote(v) for k,v in fields.items())+'},\n'
        book_text+='['+quote(identifier)+']={title='+quote(fields['title'])+',parts={'+''.join('{key='+quote(k)+',text='+quote(strings[k])+',source="local installation"},' for k in b['parts'])+'}},\n'
    book_index+='}\nfor _,r in pairs(KCD2BookClassIndex) do local k=r.titleKey;KCD2BookItemIndex[k]=KCD2BookItemIndex[k] or {};table.insert(KCD2BookItemIndex[k],r) end\n'
    book_text+='}\n'
    return dict(zip(LOCAL_FILES,(index,text,book_index,book_text))),articles,speech_books,{'codex_entries':len(codex),'books':len(books),'language':language,'inputs':inputs,'tables_size':tables.stat().st_size,'tables_mtime_ns':tables.stat().st_mtime_ns}

def publish(mod, lua, articles, books, metadata):
    # Prepare everything before replacing anything. Roll back on publication failure.
    (mod/'Build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='catalogue-',dir=mod/'Build') as temp:
        temp=Path(temp);pak=temp/'catalogue.pak'
        with zipfile.ZipFile(pak,'w',compression=zipfile.ZIP_STORED) as z:
            for name,data in lua.items():z.writestr('Scripts/Mods/'+name,data.encode('utf8'))
        targets={mod/'Build/english_articles.json':json.dumps(articles,ensure_ascii=False).encode('utf8'),
          mod/'Build/book_english_text.json':json.dumps(books,ensure_ascii=False).encode('utf8'),
          mod/'Data/reader_local_catalogue.pak':pak.read_bytes()}
        metadata['outputs']={str(p.relative_to(mod)):hashlib.sha256(data).hexdigest() for p,data in targets.items()}
        targets[mod/'Build/catalogue-ready.json']=json.dumps(metadata,indent=2).encode('utf8')
        old={p:p.read_bytes() if p.exists() else None for p in targets}
        done=[]
        try:
            for i,(target,data) in enumerate(targets.items()):
                staged=temp/str(i);staged.write_bytes(data);os.replace(staged,target);done.append(target)
        except Exception:
            for target in reversed(done):
                if old[target] is None:target.unlink(missing_ok=True)
                else:
                    rollback=temp/'rollback';rollback.write_bytes(old[target]);os.replace(rollback,target)
            raise

def main():
    parser=argparse.ArgumentParser(description='Build private English reading catalogue with KCD2 closed')
    parser.add_argument('--game-root',type=Path)
    args=parser.parse_args()
    mod=Path(__file__).resolve().parent.parent
    game=args.game_root.resolve() if args.game_root else mod.parent.parent
    if game_running():raise RuntimeError('Close KCD2 before setting up or refreshing the reader')
    if mod.name!=MOD_ID or mod.parent.name.lower()!='mods' or game!=(mod.parent.parent):
        raise RuntimeError('Install this folder as KingdomComeDeliverance2/Mods/codex_and_book_reader first')
    result=collect(game)
    if game_running():raise RuntimeError('KCD2 started during setup; close it and try again')
    publish(mod,*result)
    print('Ready: %d Codex entries and %d books. Start KCD2 normally.'%(result[3]['codex_entries'],result[3]['books']))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('SETUP FAILED:',str(exc));raise SystemExit(1)
