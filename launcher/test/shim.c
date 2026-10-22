#define _GNU_SOURCE
#include "windows.h"
#include <stdio.h>
#include <wchar.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <fcntl.h>
#include <stdint.h>

static void w2u(const wchar_t *w, char *out, size_t cap, int fixslash) {
    size_t n = 0;
    for (; *w && n + 5 < cap; w++) {
        unsigned c = (unsigned)*w;
        if (fixslash && c == '\\') c = '/';
        if (c < 0x80) out[n++] = (char)c;
        else if (c < 0x800) { out[n++] = 0xC0 | (c >> 6); out[n++] = 0x80 | (c & 63); }
        else { out[n++] = 0xE0 | (c >> 12); out[n++] = 0x80 | ((c >> 6) & 63); out[n++] = 0x80 | (c & 63); }
    }
    out[n] = 0;
}
static void u2w(const char *s, wchar_t *out, size_t cap, int towin) {
    size_t n = 0;
    while (*s && n + 1 < cap) {
        unsigned char c = (unsigned char)*s; unsigned cp;
        if (c < 0x80) { cp = c; s++; }
        else if ((c & 0xE0) == 0xC0) { cp = ((c & 31) << 6) | (s[1] & 63); s += 2; }
        else { cp = ((c & 15) << 12) | ((s[1] & 63) << 6) | (s[2] & 63); s += 3; }
        if (towin && cp == '/') cp = '\\';
        out[n++] = (wchar_t)cp;
    }
    out[n] = 0;
}
static void logf_(const char *fmt, ...) {
    const char *p = getenv("CK_TEST_LOG"); if (!p) return;
    FILE *f = fopen(p, "a"); if (!f) return;
    __builtin_va_list ap; __builtin_va_start(ap, fmt); vfprintf(f, fmt, ap); __builtin_va_end(ap); fputc('\n', f); fclose(f);
}

int lstrlenW(LPCWSTR s) { return (int)wcslen(s); }
LPWSTR lstrcpynW(LPWSTR d, LPCWSTR s, int n) { int i = 0; for (; i < n - 1 && s[i]; i++) d[i] = s[i]; if (n > 0) d[i] = 0; return d; }
int lstrcmpiW(LPCWSTR a, LPCWSTR b) { return wcscasecmp(a, b); }

DWORD GetFileAttributesW(LPCWSTR p) {
    char u[4096]; struct stat st; w2u(p, u, sizeof u, 1);
    if (stat(u, &st) != 0) return INVALID_FILE_ATTRIBUTES;
    return S_ISDIR(st.st_mode) ? FILE_ATTRIBUTE_DIRECTORY : 0x80;
}
DWORD GetModuleFileNameW(HINSTANCE m, LPWSTR buf, DWORD n) { (void)m; u2w(getenv("CK_TEST_EXE"), buf, n, 1); return (DWORD)wcslen(buf); }
LPWSTR GetCommandLineW(void) { static wchar_t b[32768]; u2w(getenv("CK_TEST_CMDLINE"), b, 32768, 0); return b; }
DWORD SearchPathW(LPCWSTR path, LPCWSTR file, LPCWSTR ext, DWORD n, LPWSTR buf, LPWSTR *part) {
    (void)path; (void)ext; (void)part;
    const char *dirs = getenv("CK_TEST_PATH"); if (!dirs) return 0;
    char f[256], d[4096], cand[4600]; w2u(file, f, sizeof f, 0); snprintf(d, sizeof d, "%s", dirs);
    for (char *t = strtok(d, ":"); t; t = strtok(NULL, ":")) {
        struct stat st; snprintf(cand, sizeof cand, "%s/%s", t, f);
        if (stat(cand, &st) == 0) { wchar_t w[4600]; u2w(cand, w, 4600, 1); if ((DWORD)wcslen(w) >= n) return (DWORD)wcslen(w) + 1; wcscpy(buf, w); return (DWORD)wcslen(w); }
    }
    return 0;
}

typedef struct { int magic; pid_t pid; int done; int code; } Proc;      /* magic 1 */
typedef struct { int magic; int fd; } File;                           /* magic 2 */
BOOL CreateProcessW(LPCWSTR app, LPWSTR cmd, void *pa, void *ta, BOOL inh, DWORD flags, void *env, LPCWSTR cwd, STARTUPINFOW *si, PROCESS_INFORMATION *pi) {
    (void)app; (void)pa; (void)ta; (void)env;
    char u[40000]; w2u(cmd, u, sizeof u, 0);
    logf_("SPAWN flags=0x%x cmd=%s", flags, u);
    /* split like CommandLineToArgvW (quotes group, no escapes) */
    char *argv[512]; int argc = 0; char *p = u;
    while (*p) {
        while (*p == ' ') p++;
        if (!*p) break;
        char *start;
        if (*p == '"') { p++; start = p; while (*p && *p != '"') p++; if (*p) *p++ = 0; }
        else { start = p; while (*p && *p != ' ') p++; if (*p) *p++ = 0; }
        for (char *q = start; *q; q++) if (*q == '\\') *q = '/';
        argv[argc++] = start;
    }
    argv[argc] = NULL;
    char cwdu[4096]; w2u(cwd, cwdu, sizeof cwdu, 1);
    pid_t pid = fork();
    if (pid < 0) return FALSE;
    if (pid == 0) {
        if (inh && (si->dwFlags & STARTF_USESTDHANDLES)) {      /* like inherited std handles: shared file offset */
            if (si->hStdInput != INVALID_HANDLE_VALUE) dup2(((File *)si->hStdInput)->fd, 0);
            if (si->hStdOutput != INVALID_HANDLE_VALUE) { dup2(((File *)si->hStdOutput)->fd, 1); dup2(((File *)si->hStdError)->fd, 2); }
        }
        if (chdir(cwdu) != 0) _exit(126);
        execv(argv[0], argv);
        _exit(127);
    }
    Proc *pr = calloc(1, sizeof *pr); pr->magic = 1; pr->pid = pid; pi->hProcess = pr; pi->hThread = calloc(1, 1);
    return TRUE;
}
DWORD WaitForSingleObject(HANDLE h, DWORD ms) {
    Proc *p = h; int st;
    if (p->done) return WAIT_OBJECT_0;
    struct timespec ts = {0, 10 * 1000 * 1000}; DWORD waited = 0;
    for (;;) {
        pid_t r = waitpid(p->pid, &st, ms == INFINITE ? 0 : WNOHANG);
        if (r == p->pid) { p->done = 1; p->code = WIFEXITED(st) ? WEXITSTATUS(st) : 0xC0000005u; return WAIT_OBJECT_0; }
        if (ms == INFINITE) continue;
        if (waited >= ms) return WAIT_TIMEOUT;
        nanosleep(&ts, NULL); waited += 10;
    }
}
BOOL GetExitCodeProcess(HANDLE h, DWORD *code) { Proc *p = h; *code = p->done ? (DWORD)p->code : 259; return TRUE; }
BOOL CloseHandle(HANDLE h) { if (h && h != INVALID_HANDLE_VALUE && ((File *)h)->magic == 2) close(((File *)h)->fd); return TRUE; }
int MessageBoxW(HANDLE w, LPCWSTR text, LPCWSTR cap, unsigned type) {
    (void)w; (void)cap; char u[8192]; w2u(text, u, sizeof u, 0);
    for (char *q = u; *q; q++) if (*q == '\n') *q = '|';
    logf_("MSGBOX type=0x%x: %s", type, u);
    if (type & MB_YESNO) { const char *a = getenv("CK_TEST_ANSWER"); return (a && !strcmp(a, "yes")) ? IDYES : IDNO; }
    return IDOK;
}
DWORD GetTempPathW(DWORD n, LPWSTR buf) {
    const char *t = getenv("CK_TEST_TEMP"); if (!t) return 0;
    wchar_t w[4096]; u2w(t, w, 4096, 1); size_t l = wcslen(w); if (l + 2 > n) return (DWORD)l + 2;
    wcscpy(buf, w); if (buf[l - 1] != L'\\') { buf[l] = L'\\'; buf[l + 1] = 0; l++; } return (DWORD)l;
}
HANDLE CreateFileW(LPCWSTR path, DWORD access, DWORD share, SECURITY_ATTRIBUTES *sa, DWORD disp, DWORD attrs, HANDLE tmpl) {
    (void)share; (void)sa; (void)attrs; (void)tmpl;
    char u[4096]; w2u(path, u, sizeof u, 1);
    if (!strcasecmp(u, "NUL")) strcpy(u, "/dev/null");
    int fl = (access & GENERIC_WRITE) ? ((access & GENERIC_READ) ? O_RDWR : O_WRONLY) : O_RDONLY;
    if (disp == CREATE_ALWAYS) fl |= O_CREAT | O_TRUNC;
    int fd = open(u, fl, 0644); if (fd < 0) return INVALID_HANDLE_VALUE;
    File *f = calloc(1, sizeof *f); f->magic = 2; f->fd = fd; return f;
}
DWORD GetFileSize(HANDLE h, DWORD *high) { (void)high; struct stat st; if (fstat(((File *)h)->fd, &st)) return INVALID_FILE_SIZE; return (DWORD)st.st_size; }
DWORD SetFilePointer(HANDLE h, LONG dist, LONG *high, DWORD method) { (void)high; (void)method; off_t r = lseek(((File *)h)->fd, dist, SEEK_SET); return r < 0 ? INVALID_SET_FILE_POINTER : (DWORD)r; }
BOOL ReadFile(HANDLE h, void *buf, DWORD n, DWORD *got, void *ov) { (void)ov; ssize_t r = read(((File *)h)->fd, buf, n); if (r < 0) return FALSE; *got = (DWORD)r; return TRUE; }
int MultiByteToWideChar(unsigned cp, DWORD flags, const char *src, int n, LPWSTR dst, int cap) {
    (void)cp; (void)flags; int i = 0; for (; i < n && i < cap; i++) dst[i] = (unsigned char)src[i]; return i;
}
extern int WinMain(HINSTANCE, HINSTANCE, LPSTR, int);
int main(void) { return WinMain(NULL, NULL, NULL, 0); }
