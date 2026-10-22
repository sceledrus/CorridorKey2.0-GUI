/*
 * CorridorKey2.exe - tiny native launcher for the CorridorKey 2.0 GUI (a GUI for CorridorKey 2.0).
 *
 * What it does (and all it does):
 *   1. Finds run_gui.py next to this exe.
 *   2. Finds Python: <folder>\venv, <folder>\.venv or <folder>\env first (the venv the CorridorKey
 *      README tells you to create), otherwise python.exe on PATH.
 *   3. Checks that Python can import PySide6 and OpenCV/numpy ("python -c import ..."), independent of
 *      which version of run_gui.py is in the folder. If PySide6 is simply not installed it asks before
 *      running "python -m pip install PySide6-Essentials" in a visible console window. Any other
 *      failure is shown together with Python's own error text.
 *   4. Starts "pythonw run_gui.py <your arguments>" (no console window) and exits. Files or folders
 *      dropped on the exe are passed straight through as arguments.
 *
 * Python's output during steps 3-4 goes to %TEMP%\corridorkey2_launcher.log so it can be shown in a
 * dialog (there is no console to print to). The launcher does not touch the network or the registry,
 * and installs nothing without asking.
 * Build: see build.py (zig cc, no Windows needed).
 */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdarg.h>

#define TITLE   L"CorridorKey 2.0"
#define PATHLEN (MAX_PATH * 2)
#define CMDLEN  32768
#define MSGLEN  4096
#define TAILLEN 1100

/* run_gui.py versions that contain this text write their own crash dialog/log (see run_gui.py) */
#define SCRIPT_MARKER "ck2-launcher:crash-report"

static const wchar_t PYSIDE_ARGS[] = L"-c \"import PySide6.QtWidgets\"";
static const wchar_t CV_ARGS[]     = L"-c \"import cv2, numpy\"";

static wchar_t g_dir[PATHLEN];      /* folder containing this exe */
static wchar_t g_script[PATHLEN];   /* <dir>\run_gui.py */
static wchar_t g_py[PATHLEN];       /* python.exe  (console build: used for checks and pip) */
static wchar_t g_pyw[PATHLEN];      /* pythonw.exe (no console: used for the GUI) */
static wchar_t g_cmd[CMDLEN];

/* ---- tiny string helpers (kernel32 only, no C runtime needed) ---- */
static void cat(wchar_t *dst, int cap, const wchar_t *s)
{
    int n = lstrlenW(dst);
    if (n < cap - 1) lstrcpynW(dst + n, s, cap - n);
}

static void join(wchar_t *dst, int cap, const wchar_t *a, const wchar_t *b)
{
    lstrcpynW(dst, a, cap);
    cat(dst, cap, L"\\");
    cat(dst, cap, b);
}

static int file_exists(const wchar_t *p)
{
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static int contains_ci(const wchar_t *hay, const wchar_t *needle)
{
    int hn = lstrlenW(hay), nn = lstrlenW(needle);
    for (int i = 0; i + nn <= hn; i++) {
        int k = 0;
        while (k < nn && (hay[i + k] | 0x20) == (needle[k] | 0x20)) k++;
        if (k == nn) return 1;
    }
    return 0;
}

static void num(wchar_t *dst, DWORD v)   /* unsigned decimal, no CRT */
{
    wchar_t tmp[16];
    int n = 0;
    if (v == 0) tmp[n++] = L'0';
    while (v) { tmp[n++] = (wchar_t)(L'0' + v % 10); v /= 10; }
    int i = 0;
    while (n) dst[i++] = tmp[--n];
    dst[i] = 0;
}

/* ---- message boxes ---- */
/* fail(part, part, ..., NULL): the parts are joined into one error box */
static void fail(const wchar_t *first, ...)
{
    wchar_t buf[MSGLEN];
    va_list ap;
    buf[0] = 0;
    va_start(ap, first);
    for (const wchar_t *s = first; s; s = va_arg(ap, const wchar_t *)) cat(buf, MSGLEN, s);
    va_end(ap);
    MessageBoxW(NULL, buf, TITLE, MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
}

/* ---- capturing a child's output (it has no console to print to) ---- */
static HANDLE open_inheritable(const wchar_t *path, DWORD access, DWORD disposition)
{
    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof sa;
    sa.lpSecurityDescriptor = NULL;
    sa.bInheritHandle = TRUE;
    return CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, disposition, FILE_ATTRIBUTE_NORMAL, NULL);
}

static HANDLE open_log(void)         /* %TEMP%\corridorkey2_launcher.log, emptied */
{
    wchar_t p[PATHLEN];
    DWORD n = GetTempPathW(PATHLEN, p);
    if (n == 0 || n >= PATHLEN - 40) return INVALID_HANDLE_VALUE;
    cat(p, PATHLEN, L"corridorkey2_launcher.log");
    return open_inheritable(p, GENERIC_READ | GENERIC_WRITE, CREATE_ALWAYS);
}

/* Last ~1 KB of the log as text, carriage returns removed. Only call once the writer has exited. */
static void read_tail(HANDLE h, wchar_t *dst, int cap)
{
    char raw[1024];
    DWORD size, want, got = 0;
    int n, j = 0;
    dst[0] = 0;
    if (h == INVALID_HANDLE_VALUE) return;
    size = GetFileSize(h, NULL);
    if (size == INVALID_FILE_SIZE || size == 0) return;
    want = size < sizeof raw ? size : (DWORD)sizeof raw;
    if (SetFilePointer(h, (LONG)(size - want), NULL, FILE_BEGIN) == INVALID_SET_FILE_POINTER) return;
    if (!ReadFile(h, raw, want, &got, NULL) || got == 0) return;
    n = MultiByteToWideChar(CP_ACP, 0, raw, (int)got, dst, cap - 1);
    for (int i = 0; i < n; i++)
        if (dst[i] != L'\r') dst[j++] = dst[i];
    while (j > 0 && (dst[j - 1] == L'\n' || dst[j - 1] == L' ')) j--;
    dst[j] = 0;
}

/* ASCII text anywhere in the first 16 KB of a file */
static int file_has(const wchar_t *path, const char *needle)
{
    char buf[16384];
    DWORD got = 0;
    int nn = 0;
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    if (!ReadFile(h, buf, sizeof buf, &got, NULL)) got = 0;
    CloseHandle(h);
    while (needle[nn]) nn++;
    for (DWORD i = 0; i + nn <= got; i++) {
        int k = 0;
        while (k < nn && buf[i + k] == needle[k]) k++;
        if (k == nn) return 1;
    }
    return 0;
}

/* ---- processes ---- */
/* Runs "<exe>" <args> in g_dir. If out is valid, its stdout and stderr go there (stdin is NUL). */
static int start(const wchar_t *exe, const wchar_t *args, DWORD flags, HANDLE out, PROCESS_INFORMATION *pi)
{
    STARTUPINFOW si;
    HANDLE in = INVALID_HANDLE_VALUE;
    BOOL inherit = FALSE;
    int ok;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    g_cmd[0] = 0;
    cat(g_cmd, CMDLEN, L"\"");
    cat(g_cmd, CMDLEN, exe);
    cat(g_cmd, CMDLEN, L"\" ");
    cat(g_cmd, CMDLEN, args);
    if (lstrlenW(g_cmd) >= CMDLEN - 2) return 0;
    if (out != INVALID_HANDLE_VALUE) {
        in = open_inheritable(L"NUL", GENERIC_READ, OPEN_EXISTING);
        si.dwFlags = STARTF_USESTDHANDLES;
        si.hStdInput = in;
        si.hStdOutput = out;
        si.hStdError = out;
        inherit = TRUE;
    }
    ok = CreateProcessW(NULL, g_cmd, NULL, NULL, inherit, flags, NULL, g_dir, &si, pi) ? 1 : 0;
    if (in != INVALID_HANDLE_VALUE) CloseHandle(in);
    return ok;
}

static int run_wait(const wchar_t *exe, const wchar_t *args, DWORD flags, HANDLE out, DWORD *code)
{
    PROCESS_INFORMATION pi;
    if (!start(exe, args, flags, out, &pi)) return 0;
    WaitForSingleObject(pi.hProcess, INFINITE);
    *code = 0;
    GetExitCodeProcess(pi.hProcess, code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 1;
}

/* Runs a hidden python check; returns 0 if Python could not even be started. tail gets its output. */
static int probe(const wchar_t *args, DWORD *code, wchar_t *tail)
{
    HANDLE log = open_log();
    int ok = run_wait(g_py, args, CREATE_NO_WINDOW, log, code);
    read_tail(log, tail, TAILLEN);
    if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
    return ok;
}

/* ---- finding python ---- */
static int find_python(void)
{
    static const wchar_t *venvs[] = { L"venv", L".venv", L"env", 0 };
    for (int i = 0; venvs[i]; i++) {
        wchar_t rel[PATHLEN];
        join(rel, PATHLEN, g_dir, venvs[i]);
        join(g_py, PATHLEN, rel, L"Scripts\\python.exe");
        if (file_exists(g_py)) {
            join(g_pyw, PATHLEN, rel, L"Scripts\\pythonw.exe");
            if (!file_exists(g_pyw)) lstrcpynW(g_pyw, g_py, PATHLEN);
            return 1;
        }
    }
    wchar_t found[PATHLEN];
    DWORD n = SearchPathW(NULL, L"python.exe", NULL, PATHLEN, found, NULL);
    /* the Microsoft Store "python.exe" under WindowsApps is only a stub that opens the Store */
    if (n == 0 || n >= PATHLEN || contains_ci(found, L"\\WindowsApps\\")) return 0;
    lstrcpynW(g_py, found, PATHLEN);
    int cut = lstrlenW(found);
    while (cut > 0 && found[cut - 1] != L'\\') cut--;
    if (cut > 0) found[cut - 1] = 0;                 /* drop the trailing '\' so join() does not double it */
    join(g_pyw, PATHLEN, found, L"pythonw.exe");
    if (!file_exists(g_pyw)) lstrcpynW(g_pyw, g_py, PATHLEN);
    return 1;
}

static const wchar_t *skip_exe_name(const wchar_t *c)
{
    if (*c == L'"') {
        c++;
        while (*c && *c != L'"') c++;
        if (*c) c++;
    } else {
        while (*c && *c != L' ' && *c != L'\t') c++;
    }
    while (*c == L' ' || *c == L'\t') c++;
    return c;
}

/* "<headline>\n\n<python.exe>\n\nPython said (exit code N):\n\n<output>\n\n<advice>" */
static void fail_python(const wchar_t *headline, DWORD code, const wchar_t *tail, const wchar_t *advice)
{
    wchar_t c[16];
    num(c, code);
    fail(headline, L"\n\n", g_py, L"\n\nPython said (exit code ", c, L"):\n\n",
         tail[0] ? tail : L"(nothing - Python may be damaged or blocked)", L"\n\n", advice, NULL);
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmdline, int show)
{
    wchar_t tail[TAILLEN];
    DWORD code = 0;
    (void)inst; (void)prev; (void)cmdline; (void)show;

    /* 1. our own folder */
    DWORD n = GetModuleFileNameW(NULL, g_dir, PATHLEN);
    if (n == 0 || n >= PATHLEN) { fail(L"Could not work out where CorridorKey2.exe is.", NULL); return 1; }
    while (n > 0 && g_dir[n - 1] != L'\\') n--;
    if (n > 3) n--;                      /* drop the trailing '\' (but keep "C:\") */
    g_dir[n] = 0;

    join(g_script, PATHLEN, g_dir, L"run_gui.py");
    if (!file_exists(g_script)) {
        fail(L"run_gui.py was not found next to CorridorKey2.exe.\n\nPut CorridorKey2.exe in the CorridorKey 2.0 "
             L"folder (the one that contains infer.py and run_gui.py).\n\nLooked in:\n", g_dir, NULL);
        return 1;
    }

    /* 2. python */
    if (!find_python()) {
        fail(L"Python was not found.\n\nCorridorKey 2.0 runs in the Python environment from its setup "
             L"(a folder called \"venv\" next to this exe). Create it as described in the CorridorKey README:\n\n"
             L"    python -m venv venv\n\nthen run CorridorKey2.exe again.\n\nLooked in:\n", g_dir, NULL);
        return 1;
    }

    /* 3a. PySide6, with an offer to install it when it is simply not there */
    if (!probe(PYSIDE_ARGS, &code, tail)) { fail(L"Could not start Python:\n\n", g_py, NULL); return 1; }
    if (code != 0) {
        if (!contains_ci(tail, L"No module named")) {
            fail_python(L"Python could not load PySide6 (the window toolkit) from:", code, tail,
                        L"To see more, run this in a terminal in the CorridorKey folder:\n\n"
                        L"    venv\\Scripts\\python -c \"import PySide6.QtWidgets\"");
            return 1;
        }
        wchar_t q[MSGLEN];
        q[0] = 0;
        cat(q, MSGLEN, L"The CorridorKey window needs the PySide6 package, which is not installed in:\n\n");
        cat(q, MSGLEN, g_py);
        cat(q, MSGLEN, L"\n\nInstall it now?\n(pip install PySide6-Essentials - about 80 MB. A console window shows the progress.)");
        if (MessageBoxW(NULL, q, TITLE, MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND) != IDYES) return 1;

        DWORD pip = 0;
        if (!run_wait(g_py, L"-m pip install PySide6-Essentials", CREATE_NEW_CONSOLE, INVALID_HANDLE_VALUE, &pip) || pip != 0) {
            wchar_t c[16];
            num(c, pip);
            fail(L"The PySide6 install did not finish (exit code ", c,
                 L").\n\nOpen a terminal in the CorridorKey folder and run this to see the error:\n\n"
                 L"    venv\\Scripts\\python -m pip install PySide6-Essentials", NULL);
            return 1;
        }
        if (!probe(PYSIDE_ARGS, &code, tail)) { fail(L"Could not start Python:\n\n", g_py, NULL); return 1; }
        if (code != 0) {
            fail_python(L"PySide6 was installed but Python still cannot load it from:", code, tail,
                        L"To see more, run this in a terminal in the CorridorKey folder:\n\n"
                        L"    venv\\Scripts\\python -c \"import PySide6.QtWidgets\"");
            return 1;
        }
    }

    /* 3b. OpenCV and numpy (installed by the CorridorKey requirements, so no install offer) */
    if (!probe(CV_ARGS, &code, tail)) { fail(L"Could not start Python:\n\n", g_py, NULL); return 1; }
    if (code != 0) {
        fail_python(L"OpenCV or numpy could not be loaded from:", code, tail,
                    L"Install the CorridorKey requirements first:\n\n    venv\\Scripts\\python -m pip install -r requirements.txt");
        return 1;
    }

    /* 4. launch the GUI with whatever was dropped on / passed to this exe */
    wchar_t args[CMDLEN];
    args[0] = 0;
    cat(args, CMDLEN, L"\"");
    cat(args, CMDLEN, g_script);
    cat(args, CMDLEN, L"\" ");
    cat(args, CMDLEN, skip_exe_name(GetCommandLineW()));
    if (lstrlenW(args) >= CMDLEN - 2) { fail(L"Too many files were dropped at once.", NULL); return 1; }

    PROCESS_INFORMATION pi;
    HANDLE log = open_log();
    DWORD flags = (lstrcmpiW(g_pyw, g_py) == 0) ? CREATE_NO_WINDOW : 0;
    if (!start(g_pyw, args, flags, log, &pi)) {
        fail(L"Could not start the CorridorKey window:\n\n", g_pyw, NULL);
        return 1;
    }
    /* If it dies right away, say why: there is no console, so a broken install would fail silently.
       Exit code 1 is the GUI's own "already reported" code, but only for run_gui.py versions that carry
       the marker; an older copy just crashes with 1, so that one is not silent. */
    if (WaitForSingleObject(pi.hProcess, 4000) == WAIT_OBJECT_0) {
        GetExitCodeProcess(pi.hProcess, &code);
        int reported = file_has(g_script, SCRIPT_MARKER);
        if (code != 0 && !(code == 1 && reported)) {
            wchar_t c[16];
            const wchar_t *hint;
            num(c, code);
            read_tail(log, tail, TAILLEN);
            if (code == 0xC0000135u)
                hint = L"A required DLL is missing. Install the Microsoft Visual C++ Redistributable (x64) and try again.";
            else if (!reported)
                hint = L"The run_gui.py in this folder is older than this CorridorKey2.exe. Replace it with the one from "
                       L"the same download (copy the whole zip over the CorridorKey folder).";
            else
                hint = L"Run this in a terminal in the CorridorKey folder to see why:\n\n    venv\\Scripts\\python run_gui.py";
            fail(L"CorridorKey closed right after starting (exit code ", c, L").\n\n", hint,
                 tail[0] ? L"\n\nPython said:\n\n" : L"", tail, NULL);
        }
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
    return 0;
}
