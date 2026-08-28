"""Check the tray menu tree without ever displaying it."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import screentuner as sp

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "menu_test.json")

fails = []


def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        fails.append(label)


def make_app(n):
    cfg = {"settings": {}, "hotkeys": {"neutral": "ctrl+alt+0", "quit": "ctrl+alt+q"},
           "profiles": [{"name": f"Profile {i+1}", "hotkey": None, "vibrance": 50}
                        for i in range(n)]}
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return sp.App(CFG, use_tray=False)


def summarise(items):
    inline = [e for e in items if e and e[0] == "item" and e[1] >= sp.CMD_BASE]
    subs = [e for e in items if e and e[0] == "submenu"]
    return inline, subs


print("=== 6 profiles: everything inline, no submenu ===")
app = make_app(6)
inline, subs = summarise(app._menu_items())
check("all 6 shown inline", len(inline) == 6)
check("no submenu", len(subs) == 0)

print("\n=== 20 profiles: overflow into a submenu ===")
app = make_app(20)
items = app._menu_items()
inline, subs = summarise(items)
print(f"   inline={len(inline)} submenu={len(subs)} "
      f"children={len(subs[0][2]) if subs else 0}")
check("inline capped at the limit-1", len(inline) == sp.MENU_PROFILE_LIMIT - 1)
check("one submenu", len(subs) == 1)
check("submenu holds the remainder",
      len(subs[0][2]) == 20 - (sp.MENU_PROFILE_LIMIT - 1))
check("every profile reachable exactly once",
      sorted(e[1] for e in inline + subs[0][2]) ==
      list(range(sp.CMD_BASE, sp.CMD_BASE + 20)))
check("submenu label names the count", "(9)" in subs[0][1])

print("\n=== active profile living in the overflow gets promoted ===")
app.current = 17                       # well past the inline limit
items = app._menu_items()
inline, subs = summarise(items)
ids = [e[1] - sp.CMD_BASE for e in inline]
print("   inline ids:", ids)
check("active profile pulled into the visible list", 17 in ids)
check("it is the checked one", any(e[1] - sp.CMD_BASE == 17 and e[3] for e in inline))
check("still no duplicates",
      sorted(e[1] for e in inline + subs[0][2]) ==
      list(range(sp.CMD_BASE, sp.CMD_BASE + 20)))
check("header reflects the active profile",
      "Profile 18" in items[0][2])

print("\n=== the tree actually builds into real HMENUs ===")
h = app._build_menu(app._menu_items())
check("root menu created", bool(h))
count = sp.user32.GetMenuItemCount(h)
print("   root item count:", count)
check("root has the expected item count", count == len(app._menu_items()))
destroyed = sp.user32.DestroyMenu(h)
check("DestroyMenu reported success", bool(destroyed))
check("the handle is no longer a menu", not sp.user32.IsMenu(h))

print("\n=== command routing covers every menu id ===")
missing = [e[1] for e in app._menu_items()
           if e and e[0] == "item" and e[1] and e[1] < sp.CMD_BASE
           and e[1] not in sp.MENU_ACTIONS]
print("   unrouted ids:", missing)
check("every non-profile item maps to an action", not missing)
check("every action name exists on the app",
      all(n in app.actions for n in sp.MENU_ACTIONS.values()))

app.nv.unload()
os.remove(CFG)
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
