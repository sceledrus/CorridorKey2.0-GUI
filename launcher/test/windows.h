/* Minimal Win32 shim so launcher.c can be compiled and run on Linux for control-flow testing only. */
#pragma once
#include <stddef.h>
#include <stdint.h>
typedef uint32_t DWORD; typedef int32_t LONG; typedef int BOOL; typedef void *HANDLE; typedef void *HINSTANCE; typedef char *LPSTR;
typedef wchar_t *LPWSTR; typedef const wchar_t *LPCWSTR;
#define WINAPI
#define MAX_PATH 260
#define TRUE 1
#define FALSE 0
#define INVALID_FILE_ATTRIBUTES 0xFFFFFFFFu
#define FILE_ATTRIBUTE_DIRECTORY 0x10
#define CREATE_NO_WINDOW 0x08000000
#define CREATE_NEW_CONSOLE 0x00000010
#define MB_OK 0
#define MB_YESNO 4
#define MB_ICONERROR 0x10
#define MB_ICONQUESTION 0x20
#define MB_SETFOREGROUND 0x10000
#define IDOK 1
#define IDYES 6
#define IDNO 7
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define INVALID_FILE_SIZE 0xFFFFFFFFu
#define INVALID_SET_FILE_POINTER ((DWORD)-1)
#define FILE_BEGIN 0
#define GENERIC_READ 0x80000000u
#define GENERIC_WRITE 0x40000000u
#define FILE_SHARE_READ 1
#define FILE_SHARE_WRITE 2
#define CREATE_ALWAYS 2
#define OPEN_EXISTING 3
#define FILE_ATTRIBUTE_NORMAL 0x80
#define STARTF_USESTDHANDLES 0x100
#define CP_ACP 0
#define WAIT_OBJECT_0 0
#define WAIT_TIMEOUT 258
#define INFINITE 0xFFFFFFFFu
typedef struct { DWORD cb; DWORD dwFlags; HANDLE hStdInput; HANDLE hStdOutput; HANDLE hStdError; } STARTUPINFOW;
typedef struct { DWORD nLength; void *lpSecurityDescriptor; BOOL bInheritHandle; } SECURITY_ATTRIBUTES;
typedef struct { HANDLE hProcess; HANDLE hThread; DWORD dwProcessId; DWORD dwThreadId; } PROCESS_INFORMATION;
#define ZeroMemory(p, n) __builtin_memset((p), 0, (n))
int lstrlenW(LPCWSTR s); LPWSTR lstrcpynW(LPWSTR d, LPCWSTR s, int n); int lstrcmpiW(LPCWSTR a, LPCWSTR b);
DWORD GetFileAttributesW(LPCWSTR p); DWORD SearchPathW(LPCWSTR path, LPCWSTR file, LPCWSTR ext, DWORD n, LPWSTR buf, LPWSTR *part);
DWORD GetModuleFileNameW(HINSTANCE m, LPWSTR buf, DWORD n); LPWSTR GetCommandLineW(void);
BOOL CreateProcessW(LPCWSTR app, LPWSTR cmd, void *pa, void *ta, BOOL inh, DWORD flags, void *env, LPCWSTR cwd, STARTUPINFOW *si, PROCESS_INFORMATION *pi);
DWORD WaitForSingleObject(HANDLE h, DWORD ms); BOOL GetExitCodeProcess(HANDLE h, DWORD *code); BOOL CloseHandle(HANDLE h);
int MessageBoxW(HANDLE w, LPCWSTR text, LPCWSTR cap, unsigned type);

DWORD GetTempPathW(DWORD n, LPWSTR buf);
HANDLE CreateFileW(LPCWSTR path, DWORD access, DWORD share, SECURITY_ATTRIBUTES *sa, DWORD disp, DWORD attrs, HANDLE tmpl);
DWORD GetFileSize(HANDLE h, DWORD *high); DWORD SetFilePointer(HANDLE h, LONG dist, LONG *high, DWORD method);
BOOL ReadFile(HANDLE h, void *buf, DWORD n, DWORD *got, void *ov);
int MultiByteToWideChar(unsigned cp, DWORD flags, const char *src, int n, LPWSTR dst, int cap);
