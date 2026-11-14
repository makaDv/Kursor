"""Window actions against a throw-away test window (never the user's own apps)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import subprocess, sys, time
from kursor.control import windows

TITLE = "PadLink-test-window-7731"
child = subprocess.Popen([sys.executable, "-c",
    f"import tkinter as t; r=t.Tk(); r.title('{TITLE}'); r.geometry('300x120'); r.mainloop()"])
fails = []
def check(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n, "" if ok else x)
    if not ok: fails.append(n)

def find():
    for _ in range(50):
        for w in windows.list_windows():
            if w["title"] == TITLE:
                return w
        time.sleep(0.1)
    return None

w = find(); check("test window listed", w is not None)
hid = w["id"]
windows.window_action(hid, "minimize"); time.sleep(0.4); check("minimize", find()["minimized"])
windows.window_action(hid, "restore"); time.sleep(0.4); check("restore", not find()["minimized"])
windows.window_action(hid, "maximize"); time.sleep(0.4); check("maximize", find()["maximized"])
windows.window_action(hid, "restore"); time.sleep(0.4)
windows.window_action(hid, "minimize"); time.sleep(0.3)
windows.window_action(hid, "focus")
for _ in range(20):  # up to 2 s: restore animation + foreground switch
    f = find()
    if f and f["focused"] and not f["minimized"]:
        break
    time.sleep(0.1)
check("focus restores + foreground", not f["minimized"] and f["focused"], f)
try:
    windows.window_action(123456789, "close"); check("unknown handle rejected", False)
except windows.WindowError as e:
    check("unknown handle rejected", e.code == "not_found")
ex = next((x for x in windows.list_windows() if x["exe"] == "explorer.exe"), None)
if ex:
    try:
        windows.window_action(ex["id"], "kill"); check("explorer kill refused", False)
    except windows.WindowError as e:
        check("explorer kill refused", e.code == "protected")
windows.window_action(hid, "close"); time.sleep(1.0)
check("close (WM_CLOSE) ends test window", child.poll() is not None)
if child.poll() is None:
    child.kill()

# kill path, on a second throw-away window
child2 = subprocess.Popen([sys.executable, "-c",
    f"import tkinter as t; r=t.Tk(); r.title('{TITLE}'); r.protocol('WM_DELETE_WINDOW', lambda: None); r.mainloop()"])
w2 = find()
windows.window_action(w2["id"], "close"); time.sleep(0.6)
check("app may refuse close (still running)", child2.poll() is None)
windows.window_action(w2["id"], "kill"); time.sleep(0.8)
check("kill terminates it", child2.poll() is not None)
print("RESULT:", "FAILED " + str(fails) if fails else "ALL PASSED")
