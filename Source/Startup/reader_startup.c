#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

/* Flat metadata ABI from KCSEAPI.h dataVersion 1. No C++ vtables or game APIs used. */
typedef struct {
    uint32_t dataVersion, pluginVersion;
    char name[256], author[256];
    uint32_t compatibleGameVersions[16], kcseVersionRequired, versionIndependence;
} PluginVersionData;
_Static_assert(sizeof(PluginVersionData) == 592, "KCSE metadata ABI changed");
__declspec(dllexport) PluginVersionData KCSEPlugin_Version = {
    1, 1, "Codex Reader Startup", "Codex Reader contributors", {0}, 0, 0
};

static HMODULE module;
static LONG started = 0;
static HANDLE instance_guard;
static wchar_t log_file[32768];

static bool join(wchar_t *out, size_t capacity, const wchar_t *base, const wchar_t *tail) {
    int result = swprintf(out, capacity, L"%ls\\%ls", base, tail);
    return result > 0 && (size_t)result < capacity;
}
static bool parent(wchar_t *path) {
    wchar_t *slash = wcsrchr(path, L'\\');
    if (!slash) return false;
    *slash = 0; return true;
}
static bool file_exists(const wchar_t *path) {
    DWORD attributes = GetFileAttributesW(path);
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}
static void report(const char *message, DWORD detail) {
    if (!log_file[0]) return;
    SYSTEMTIME t; GetSystemTime(&t);
    char line[1024];
    int count = snprintf(line, sizeof(line), "%04u-%02u-%02uT%02u:%02u:%02uZ gamePid=%lu %s detail=%lu\r\n",
        t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,(unsigned long)GetCurrentProcessId(),message,(unsigned long)detail);
    if (count < 0 || count >= (int)sizeof(line)) return;
    HANDLE f = CreateFileW(log_file, FILE_APPEND_DATA, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD written; WriteFile(f, line, (DWORD)count, &written, NULL); CloseHandle(f);
    }
}
static bool reader_enabled(const wchar_t *path) {
    HANDLE f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return false;
    DWORD size = GetFileSize(f, NULL);
    if (size == INVALID_FILE_SIZE || size > 1024*1024) { CloseHandle(f); return false; }
    char *text = (char*)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (SIZE_T)size+1);
    if (!text) { CloseHandle(f); return false; }
    DWORD read = 0; bool found = false;
    if (ReadFile(f, text, size, &read, NULL)) {
        char *line = text;
        if (read >= 3 && (unsigned char)text[0]==0xef && (unsigned char)text[1]==0xbb && (unsigned char)text[2]==0xbf) line+=3;
        while (*line) {
            char *end = strchr(line, '\n');
            if (end) *end=0;
            while (*line==' ' || *line=='\t') ++line;
            size_t length = strlen(line);
            while (length && (line[length-1]==' ' || line[length-1]=='\t' || line[length-1]=='\r')) line[--length]=0;
            if (_stricmp(line,"codex_and_book_reader")==0) { found=true; break; }
            if (!end) break;
            line=end+1;
        }
    }
    HeapFree(GetProcessHeap(),0,text); CloseHandle(f); return found;
}

static DWORD WINAPI bootstrap(void *unused) {
    (void)unused;
    wchar_t directory[32768], ini[32768], game[32768], order[32768], project[32768], python[32768], script[32768], game_log[32768];
    DWORD length=GetModuleFileNameW(module,directory,32768);
    if (!length || length>=32768 || !parent(directory)) return 0;
    if (!join(log_file,32768,directory,L"KCD2ReaderStartup.log") || !join(ini,32768,directory,L"KCD2ReaderStartup.ini")) return 0;
    if (!GetPrivateProfileIntW(L"Reader",L"Enabled",1,ini)) { report("DISABLED in startup INI",0); return 0; }
    length=GetModuleFileNameW(NULL,game,32768);
    if (!length || length>=32768) { report("ERROR locating game",GetLastError()); return 0; }
    const wchar_t *filename=wcsrchr(game,L'\\');
    if (!filename || _wcsicmp(filename+1,L"KingdomCome.exe")!=0) { report("REFUSED unexpected host",0); return 0; }
    if (!parent(game) || !parent(game) || !parent(game)) { report("ERROR locating game root",0); return 0; }
    if (!join(order,32768,game,L"Mods\\mod_order.txt") || (file_exists(order) && !reader_enabled(order))) { report("SKIPPED reader not active in mod_order.txt",0); return 0; }
    /* Portable mod root: DLL resides in Mods/codex_and_book_reader/KCSE/Plugins. */
    wcscpy(project,directory);
    if (!parent(project) || !parent(project)
        || !join(python,32768,project,L"Speech\\PiperCori\\python\\pythonw.exe")
        || !join(script,32768,project,L"Source\\speech_companion.py")
        || !file_exists(script) || !file_exists(python)) {
        report("ERROR incomplete reader installation",0); return 0;
    }
    wchar_t catalogue[32768];
    if (!join(catalogue,32768,project,L"Build\\catalogue-ready.json") || !file_exists(catalogue)) {
        report("SETUP REQUIRED: run Setup Reader.cmd with the game closed",0); return 0;
    }
    if (!join(game_log,32768,game,L"kcd.log")) { report("ERROR game log path",0); return 0; }
    wchar_t mutex_name[128];
    swprintf(mutex_name,128,L"Local\\KCD2CodexReaderStartup-%lu",(unsigned long)GetCurrentProcessId());
    instance_guard=CreateMutexW(NULL,FALSE,mutex_name);
    DWORD mutex_error=GetLastError();
    if (!instance_guard) { report("ERROR startup guard",mutex_error); return 0; }
    if (mutex_error==ERROR_ALREADY_EXISTS) { CloseHandle(instance_guard);instance_guard=NULL;report("SKIPPED duplicate startup",0);return 0; }
    /* Explicit executable and quoted arguments: no shell or PowerShell involved. */
    size_t capacity=wcslen(python)+wcslen(script)+wcslen(game_log)+128;
    wchar_t *command=(wchar_t*)HeapAlloc(GetProcessHeap(),0,capacity*sizeof(wchar_t));
    if (!command) { report("ERROR allocating launch arguments",0);return 0; }
    int count=swprintf(command,capacity,L"\"%ls\" \"%ls\" --game-pid %lu --game-log \"%ls\"",python,script,(unsigned long)GetCurrentProcessId(),game_log);
    if (count<0 || (size_t)count>=capacity) { HeapFree(GetProcessHeap(),0,command);report("ERROR launch argument length",0);return 0; }
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);
    PROCESS_INFORMATION child={0};
    BOOL ok=CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,project,&startup,&child);
    DWORD error=GetLastError(); HeapFree(GetProcessHeap(),0,command);
    if (!ok) { report("ERROR helper process launch",error);return 0; }
    report("STARTED helper; readiness in speech-companion.log",child.dwProcessId);
    CloseHandle(child.hThread);CloseHandle(child.hProcess);
    return 0;
}

__declspec(dllexport) bool KCSEPlugin_Load(const void *kcse) {
    (void)kcse;
    if (InterlockedCompareExchange(&started,1,0)!=0) return true;
    HANDLE thread=CreateThread(NULL,0,bootstrap,NULL,0,NULL);
    if (thread) CloseHandle(thread);
    /* Speech failures must never prevent the game or other plugins from loading. */
    return true;
}

BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved) {
    (void)reserved;
    if (reason==DLL_PROCESS_ATTACH) { module=instance;DisableThreadLibraryCalls(instance); }
    return TRUE;
}
