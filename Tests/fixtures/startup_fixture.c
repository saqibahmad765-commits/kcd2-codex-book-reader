#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdbool.h>
int wmain(int argc,wchar_t **argv) {
    if (argc!=2) return 2;
    HMODULE plugin=LoadLibraryW(argv[1]);
    if (!plugin) { printf("LOAD_ERROR %lu\n",(unsigned long)GetLastError());return 3; }
    bool (*load)(const void*)=(bool(*)(const void*))GetProcAddress(plugin,"KCSEPlugin_Load");
    if (!load || !load(NULL) || !load(NULL)) return 4;
    puts("LOADED_TWICE");fflush(stdout);
    getchar();
    return 0;
}
