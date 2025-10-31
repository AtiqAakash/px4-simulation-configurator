#!/usr/bin/env python3
"""
Beagle Sim — Simulation Suite (Ubuntu GUI)

Fixes in this build:
- Button sounds are now reliable (more fallbacks + bound to click & keyboard), and set to LOUD.
- Explicitly uses distinct, available Ubuntu system sound files for better feedback.
- Zenity file filters corrected so *.plan, *.kml, and *.ulg files show up properly.
- NEW: Persists the last-used directory for all file/folder selection dialogs.
- Home Altitude (m AMSL) input with configurable default (stored in config).
- Loud audio feedback wired to all clickable/functional UI events.
- Dynamic vehicle target list populated from PX4 directory structure.
- Color-coded log output for better readability (launch, info, error).
"""

import json, os, queue, subprocess, threading, webbrowser, xml.etree.ElementTree as ET, sys, shutil, math, io, urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Beagle Sim"
CONFIG_PATH = Path.home() / ".px4_sim_launcher.json"
CACHE_DIR = Path.home() / ".cache"
AVATAR_URL = "https://atiq.no/about-photo.jpg"
AVATAR_CACHE = CACHE_DIR / "beagle_sim_photo.png"

# ---------------- Theme ----------------
ACCENT="#2ea8ff"; ACCENT_HOVER="#1998f2"; ACCENT_DEEP="#0f7bd0"
SECONDARY="#9aa6b2"; SECONDARY_HOVER="#8d99a6"
BG="#0a0e14"; GLASS_BG="#0e1620"; GLASS_IN="#121c29"; GLASS_EDGE="#26384f"
CARD="#111827"; CARD_ALT="#0e1620"; BORDER="#1e2733"; TEXT="#e9f1fb"; MUTED="#9aa6b2"
DANGER="#ef4444"; DANGER_H="#dc2626"

# ---------------- Python deps bootstrap ----------------
PY_DEPS={"pyulog":"pyulog>=1.2.2","simplekml":"simplekml>=1.3.6","PIL":"Pillow>=10.0.0"}
def _pip_install(pkgs, log_fn=None):
    cmd=[sys.executable,"-m","pip","install","--user"]+list(pkgs)
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if log_fn: log_fn(p.stdout+"\n")
        return p.returncode==0
    except Exception as e:
        if log_fn: log_fn(f"[INSTALL] pip failed: {e}\n")
        return False
def _ensure_import(modname, spec=None, log_fn=None):
    try:
        __import__(modname); return True
    except ImportError:
        spec=spec or modname
        if log_fn: log_fn(f"[INSTALL] Missing '{modname}'. Installing: {spec}\n")
        if not _pip_install([spec], log_fn):
            if log_fn: log_fn(f"[INSTALL] Could not install {spec}\n")
            return False
        try:
            __import__(modname)
            if log_fn: log_fn(f"[INSTALL] '{modname}' installed successfully.\n")
            return True
        except Exception as e:
            if log_fn: log_fn(f"[INSTALL] Still cannot import '{modname}': {e}\n")
            return False

# ---------------- Sounds (FINAL: Distinct Ubuntu Sounds & Loud) ----------------
# Uses distinct Freedesktop sound files that should be present on most Ubuntu/Linux systems.
def play_sound(kind: str, widget: tk.Misc | None = None, *, loud: bool = True):
    """
    kind: "click","start","success","stop","error","info"
    Tries (in order): canberra-gtk-play -> paplay/aplay (distinct freedesktop files) -> Tk bell -> terminal bell.
    Always uses LOUD volume boost via paplay for clarity.
    """
    # Freedesktop Sound IDs (for canberra-gtk-play)
    ids = {
        "click": "button-pressed",
        "start": "bell",                  # Distinct, traditional start sound
        "success": "message-new-instant", # Good chime for success/completion
        "stop": "message-new-email",      # Short, distinct notification for stopping
        "error": "dialog-error",          
        "info": "dialog-information", 
    }
    sid = ids.get(kind, "dialog-information")

    # Explicit Freedesktop Sound Paths (for paplay/aplay)
    file_map = {
        "click": "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga", # Short, crisp tap
        "start": "/usr/share/sounds/freedesktop/stereo/bell.oga",
        "success": "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
        "stop": "/usr/share/sounds/freedesktop/stereo/message-new-email.oga",
        "error": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
        "info": "/usr/share/sounds/freedesktop/stereo/dialog-information.oga",
    }
    file_path = file_map.get(kind)
    
    # 1) Try canberra-gtk-play (best integration)
    canberra = shutil.which("canberra-gtk-play")
    if canberra:
        try:
            subprocess.Popen([canberra, "--id", sid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if loud:
                subprocess.Popen([canberra, "--id", sid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    # 2) Try paplay (PulseAudio - preferred for high volume control)
    if file_path and Path(file_path).exists():
        paplay = shutil.which("paplay")
        if paplay:
            try:
                # Use 98304 (~150%) volume for LOUD playback as requested
                vol = "98304"
                subprocess.Popen([paplay, "--volume", vol, file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
        
        # 3) Try aplay (ALSA - fallback)
        aplay = shutil.which("aplay")
        if aplay:
            try:
                subprocess.Popen([aplay, file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

    # 4) Fallback to Tk bell
    try:
        if widget is not None:
            widget.bell()
            if loud:
                widget.after(40, lambda: widget.bell())
            return
    except Exception:
        pass

    # 5) Fallback to Terminal bell
    try:
        print("\a", end="", flush=True)
        if loud:
            print("\a", end="", flush=True)
    except Exception:
        pass

# ---------------- Robust ULG → KML fallback (bright red track) ----------------
def _fallback_ulog_to_kml(ulg_path:str,out_path:str,downsample:int=5):
    from pyulog import ULog; import simplekml
    try: ulog=ULog(ulg_path, default_quaternion=True)
    except TypeError: ulog=ULog(ulg_path)
    lat=lon=alt=None; rec=None; scale=1.0
    for d in ulog.data_list:
        if d.name=="vehicle_global_position":
            rec=d.data; lat=rec.get("lat"); lon=rec.get("lon"); alt=rec.get("alt"); break
    if rec is None:
        for d in ulog.data_list:
            if d.name=="vehicle_gps_position":
                rec=d.data; lat=rec.get("lat"); lon=rec.get("lon"); alt=rec.get("alt"); scale=1e7; break
    if rec is None or lat is None or lon is None: raise RuntimeError("No GPS/global position topics found in ULog.")
    import math
    def f(x,s=1.0):
        try:
            v=float(x)/s; return v if math.isfinite(v) else None
        except Exception: return None
    coords=[]; last=-downsample
    for i in range(len(lat)):
        if i-last<downsample: continue
        la=f(lat[i],scale); lo=f(lon[i],scale); al=f(alt[i]) if alt is not None else 0.0
        if la is None or lo is None: continue
        if al is None: al=0.0
        coords.append((lo,la,al)); last=i
    if not coords: raise RuntimeError("No valid GPS samples extracted from ULog.")
    kml=simplekml.Kml(); ls=kml.newlinestring(name=os.path.basename(ulg_path))
    ls.coords=coords; ls.altitudemode=simplekml.AltitudeMode.absolute; ls.tessellate=1
    ls.style.linestyle.color=simplekml.Color.changealphaint(255, simplekml.Color.red); ls.style.linestyle.width=4
    kml.save(out_path)

# ---------------- GUI Base ----------------
class ThemedApp(tk.Tk):
    def __init__(self):
        super().__init__(className="beagle-sim")
        try: self.wm_class("beagle-sim")
        except Exception: pass
        try:
            self.call('tk','appname',APP_TITLE); self.call('wm','iconname','.',APP_TITLE)
        except Exception: pass
        self.title(APP_TITLE); self.geometry("1120x820"); self.minsize(940,720); self.configure(bg=BG)
        self._style(); self._load_icon()

    def _load_icon(self):
        try:
            from tkinter import PhotoImage
            for p in ["/usr/share/icons/hicolor/256x256/apps/beagle-sim.png",
                      "/usr/share/icons/hicolor/128x128/apps/beagle-sim.png",
                      str((Path(__file__).parent/"beagle-sim-256.png").resolve()),
                      str((Path(__file__).parent/"beagle-sim-128.png").resolve()),
                      str((Path(__file__).parent/"beagle-sim-64.png").resolve())]:
                if Path(p).exists():
                    self._app_icon=PhotoImage(file=p); self.iconphoto(True,self._app_icon); break
        except Exception: pass

    def _style(self):
        s=ttk.Style(self); s.theme_use("clam")
        s.configure("TFrame",background=BG)
        s.configure("Backplate.TFrame",background=GLASS_BG,relief="flat")
        s.configure("InnerPlate.TFrame",background=GLASS_IN,relief="flat")
        s.configure("Card.TFrame",background=CARD,relief="flat")
        s.configure("CardAlt.TFrame",background=CARD_ALT,relief="flat")
        s.configure("TLabel",background=BG,foreground=TEXT,font=("Ubuntu",11))
        s.configure("Card.TLabel",background=CARD,foreground=TEXT,font=("Ubuntu",11))
        s.configure("Header.TLabel",background=CARD_ALT,foreground=TEXT,font=("Ubuntu Medium",14))
        s.configure("Muted.TLabel",background=BG,foreground=MUTED,font=("Ubuntu",11))
        s.configure("Title.TLabel",background=CARD_ALT,foreground=ACCENT,font=("Ubuntu Bold",30))
        s.configure("TEntry",fieldbackground=CARD,background=CARD,foreground=TEXT,bordercolor=BORDER,insertcolor=ACCENT,padding=6)
        s.map("TEntry",bordercolor=[("focus",ACCENT)])
        s.configure("Beagle.TCombobox",fieldbackground=CARD,background=CARD,foreground=TEXT,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,padding=4)
        s.map("Beagle.TCombobox",fieldbackground=[("readonly",CARD),("!disabled",CARD)],
              foreground=[("readonly",TEXT),("!disabled",TEXT)],selectbackground=[("!disabled",CARD)],selectforeground=[("!disabled",TEXT)])
        s.configure("GlassPrimary.TButton",background=ACCENT,foreground="#061018",bordercolor="#5cc0ff",
                    darkcolor="#175c8f",lightcolor="#9bd7ff",relief="flat",padding=[18,12],font=("Ubuntu Medium",12))
        s.map("GlassPrimary.TButton",background=[("active",ACCENT_HOVER),("pressed",ACCENT_DEEP)],bordercolor=[("focus","#bfe7ff")])
        s.configure("GlassSecondary.TButton",background=SECONDARY,foreground="#0f141a",bordercolor="#b9c2cb",
                    darkcolor="#707b86",lightcolor="#cdd5dd",relief="flat",padding=[16,12],font=("Ubuntu Medium",12))
        s.map("GlassSecondary.TButton",background=[("active",SECONDARY_HOVER)],bordercolor=[("focus","#e2e8f0")])
        s.configure("GlassGhost.TButton",background=CARD,foreground=TEXT,bordercolor=BORDER,relief="groove",padding=[14,10],font=("Ubuntu Medium",11))
        s.map("GlassGhost.TButton",background=[("active","#162231")],bordercolor=[("active",ACCENT),("focus",ACCENT)])
        s.configure("GlassDanger.TButton",background=DANGER,foreground="#FFFFFF",bordercolor="#ff8a8a",
                    darkcolor="#7a1b1b",lightcolor="#ffb3b3",relief="flat",padding=[18,12],font=("Ubuntu Medium",12))
        s.map("GlassDanger.TButton",background=[("active",DANGER_H)],
              foreground=[("!disabled","#FFFFFF"),("active","#FFFFFF"),("disabled","#FFFFFF")])
        s.configure("Segment.TButton",background=GLASS_IN,foreground=TEXT,bordercolor=GLASS_EDGE,relief="flat",padding=[24,14],font=("Ubuntu Medium",13))
        s.map("Segment.TButton",background=[("active","#152131")],bordercolor=[("focus",ACCENT)])
        s.configure("SegmentActive.TButton",background=ACCENT,foreground="#061018",bordercolor="#bfe7ff",relief="flat",padding=[24,14],font=("Ubuntu Bold",13))
        self.option_add("*Text.background",CARD); self.option_add("*Text.foreground",TEXT)
        self.option_add("*Text.insertBackground",ACCENT); self.option_add("*Text.selectBackground",ACCENT)

# ---------------- App ----------------
class PX4SimApp(ThemedApp):
    def __init__(self):
        super().__init__()
        self.proc=None; self.log_queue=queue.Queue(); self._stop_reader=threading.Event(); self._log_visible=True
        
        # New variables to store last used directories
        self.ulg_last_dir = Path.home()
        self.kml_out_last_dir = Path.home() / "Documents"
        
        self._build_ui(); self._load_config(); self._poll_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------- Button helper (adds sound on click & keyboard) --------
    def _mk_button(self, parent, *, text, style, sound="click", command=None, **pack_kwargs):
        def invoke():
            play_sound(sound, widget=self, loud=True)
            if command: command()
        btn = ttk.Button(parent, text=text, style=style, command=invoke)
        # mouse click
        btn.bind("<Button-1>", lambda e: play_sound(sound, widget=self, loud=True), add="+")
        # keyboard: Space/Return
        btn.bind("<Key-Return>", lambda e: (play_sound(sound, widget=self, loud=True), invoke()), add="+")
        btn.bind("<Key-space>",  lambda e: (play_sound(sound, widget=self, loud=True), invoke()), add="+")
        btn.pack(**pack_kwargs)
        return btn

    # -------- Pillow helpers --------
    def _load_pillow(self):
        def _log(s): 
            try: self._append_log(s)
            except Exception: pass
        _ensure_import("PIL","Pillow>=10.0.0",_log)
        from PIL import Image, ImageTk, ImageDraw
        return Image, ImageTk, ImageDraw

    def _load_beagle_logo(self):
        Image, ImageTk, _ = self._load_pillow()
        for lp in ("/opt/beagle-sim/beagle.png", str((Path(__file__).parent/"beagle.png").resolve())):
            p=Path(lp)
            if p.exists():
                try:
                    img=Image.open(lp).convert("RGBA"); base_h=64; w,h=img.size
                    if h>0: img=img.resize((max(1,int(w*(base_h/h))), base_h), Image.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except Exception: return None
        return None

    def _get_circle_avatar(self, url: str, size: int = 40):
        try:
            CACHE_DIR.mkdir(parents=True,exist_ok=True)
            if not AVATAR_CACHE.exists():
                with urllib.request.urlopen(url,timeout=8) as r: AVATAR_CACHE.write_bytes(r.read())
            raw=AVATAR_CACHE.read_bytes()
        except Exception: return None
        Image, ImageTk, ImageDraw = self._load_pillow()
        try:
            img=Image.open(io.BytesIO(raw)).convert("RGBA").resize((size,size),Image.LANCZOS)
            mask=Image.new("L",(size,size),0); d=ImageDraw.Draw(mask); d.ellipse((0,0,size,size),fill=255); img.putalpha(mask)
            return ImageTk.PhotoImage(img)
        except Exception: return None

    # -------- Zenity presence --------
    def _zenity_available(self) -> bool:
        return shutil.which("zenity") is not None

    # -------- Dynamic Vehicle Targets --------
    def _get_vehicle_targets(self, px4_dir: str):
        """Finds potential vehicle targets in the PX4 firmware path."""
        path = Path(px4_dir) / "boards" / "px4" / "sitl"
        
        default_target = "gazebo_typhoon_h480" 
        
        if not path.is_dir():
            return [default_target] 
        
        targets = []
        for d in path.iterdir():
            if d.is_dir() and (d / "default.cmake").exists():
                targets.append(f"gazebo_{d.name}")
        
        return sorted(targets) if targets else [default_target]


    # -------- UI --------
    def _build_ui(self):
        # Header
        header=ttk.Frame(self,padding=(24,20),style="CardAlt.TFrame"); header.pack(fill=tk.X)
        left=ttk.Frame(header,style="CardAlt.TFrame"); left.pack(side=tk.LEFT,anchor="w")
        self._header_logo=self._load_beagle_logo()
        if self._header_logo: ttk.Label(left,image=self._header_logo,background=CARD_ALT).pack(side=tk.LEFT,padx=(0,14))
        title_col=ttk.Frame(left,style="CardAlt.TFrame"); title_col.pack(side=tk.LEFT)
        ttk.Label(title_col,text="Simulation Suite",style="Title.TLabel").pack(anchor="w")
        right=ttk.Frame(header,style="CardAlt.TFrame"); right.pack(side=tk.RIGHT,anchor="e")
        lab=ttk.Label(right,text="© Atiq",style="Header.TLabel",cursor="hand2"); lab.pack(side=tk.LEFT,padx=(0,10))
        self._avatar_img=self._get_circle_avatar(AVATAR_URL, size=40)
        if self._avatar_img:
            ava=ttk.Label(right,image=self._avatar_img,background=CARD_ALT,cursor="hand2"); ava.pack(side=tk.LEFT)
        for ch in right.winfo_children():
            ch.bind("<Button-1>", lambda e:(play_sound("info", widget=self, loud=True), webbrowser.open_new_tab("https://atiq.no")))

        # Glass backplate & segmented tabs
        plate=ttk.Frame(self,padding=18,style="Backplate.TFrame"); plate.pack(fill=tk.BOTH,expand=True,padx=16,pady=16)
        segrow=ttk.Frame(plate,padding=8,style="InnerPlate.TFrame"); segrow.pack(fill=tk.X,pady=(0,10))
        self._sim_page=ttk.Frame(plate,padding=16,style="InnerPlate.TFrame")
        self._kml_page=ttk.Frame(plate,padding=16,style="InnerPlate.TFrame")

        self._seg_sim_btn=self._mk_button(segrow, text="Simulation", style="SegmentActive.TButton",
                                          sound="click", command=lambda:self._switch_page("sim"),
                                          side=tk.LEFT, padx=(4,6))
        self._seg_kml_btn=self._mk_button(segrow, text="ULG → KML", style="Segment.TButton",
                                          sound="click", command=lambda:self._switch_page("kml"),
                                          side=tk.LEFT, padx=(6,4))

        # --- Simulation UI ---
        root=ttk.Frame(self._sim_page,padding=0,style="InnerPlate.TFrame"); root.pack(fill=tk.BOTH,expand=True)
        ttk.Label(root,text="Launch PX4 SITL with your chosen home location.",style="Muted.TLabel").pack(anchor=tk.W,pady=(0,12))

        card=ttk.Frame(root,padding=16,style="Card.TFrame"); card.pack(fill=tk.X,pady=(0,12))
        r1=ttk.Frame(card,style="Card.TFrame"); r1.pack(fill=tk.X,pady=(0,12))
        ttk.Label(r1,text="PX4 Firmware Folder",style="Card.TLabel").pack(side=tk.LEFT)
        self.px4_dir_var=tk.StringVar()
        ttk.Entry(r1,textvariable=self.px4_dir_var,width=64).pack(side=tk.LEFT,padx=10,fill=tk.X,expand=True)
        self._mk_button(r1, text="Browse", style="GlassGhost.TButton", sound="click",
                        command=self._select_px4_dir, side=tk.LEFT)

        r2=ttk.Frame(card,style="Card.TFrame"); r2.pack(fill=tk.X,pady=(0,12))
        ttk.Label(r2,text="Home Latitude (°)",style="Card.TLabel").pack(side=tk.LEFT); self.lat_var=tk.StringVar()
        ttk.Entry(r2,textvariable=self.lat_var,width=18).pack(side=tk.LEFT,padx=(8,20))
        ttk.Label(r2,text="Home Longitude (°)",style="Card.TLabel").pack(side=tk.LEFT); self.lon_var=tk.StringVar()
        ttk.Entry(r2,textvariable=self.lon_var,width=18).pack(side=tk.LEFT,padx=(8,10))
        self._mk_button(r2, text="Import from .plan/.kml", style="GlassSecondary.TButton", sound="click",
                        command=self._import_coords, side=tk.LEFT, padx=(12,0))

        r3=ttk.Frame(card,style="Card.TFrame"); r3.pack(fill=tk.X)
        ttk.Label(r3,text="Simulation Speed (×)",style="Card.TLabel").pack(side=tk.LEFT); self.speed_var=tk.StringVar(value="20")
        ttk.Entry(r3,textvariable=self.speed_var,width=12).pack(side=tk.LEFT,padx=(8,20))
        
        # Vehicle Target (Dynamically populated)
        ttk.Label(r3,text="Vehicle Target",style="Card.TLabel").pack(side=tk.LEFT); self.vehicle_var=tk.StringVar(value="gazebo_typhoon_h480")
        self.vehicle_combo=ttk.Combobox(r3,textvariable=self.vehicle_var,state="readonly",
                                        values=self._get_vehicle_targets(""),width=32,style="Beagle.TCombobox") 
        self.vehicle_combo.pack(side=tk.LEFT,padx=(8,20))
        self.vehicle_combo.bind("<<ComboboxSelected>>", lambda e: play_sound("click", widget=self, loud=True), add="+")

        # Home altitude (m AMSL) - Label Clarified
        ttk.Label(r3,text="Home Altitude (m AMSL)",style="Card.TLabel").pack(side=tk.LEFT)
        self.alt_var=tk.StringVar(value="0")  
        ttk.Entry(r3,textvariable=self.alt_var,width=12).pack(side=tk.LEFT,padx=(8,0))

        ctrls=ttk.Frame(root,padding=(0,12,0,12),style="InnerPlate.TFrame"); ctrls.pack(fill=tk.X)
        self.start_btn=self._mk_button(ctrls, text="Start Simulation", style="GlassPrimary.TButton", sound="start",
                                       command=self._start, side=tk.LEFT)
        self.stop_btn=self._mk_button(ctrls, text="Stop", style="GlassDanger.TButton", sound="stop",
                                      command=self._stop, side=tk.LEFT, padx=(10,0))
        self.stop_btn.configure(state=tk.DISABLED)
        self.toggle_logs_btn=self._mk_button(ctrls, text="Hide Logs", style="GlassGhost.TButton", sound="click",
                                             command=self._toggle_logs, side=tk.RIGHT)

        self.log_card=ttk.Labelframe(root,text="Build / Run Logs",padding=10,style="Card.TFrame")
        s=ttk.Style(self); s.configure("Card.TLabelframe",background=CARD,foreground=ACCENT)
        s.configure("Card.TLabelframe.Label",background=CARD,foreground=ACCENT,font=("Ubuntu Medium",13))
        
        # Color-coded Log Text configuration 
        self.log_text=tk.Text(self.log_card,wrap=tk.NONE,height=18,bd=0,highlightthickness=0,background=CARD,foreground=TEXT,insertbackground=ACCENT)
        self.log_text.tag_configure("info", foreground=ACCENT) 
        self.log_text.tag_configure("error", foreground=DANGER) 
        self.log_text.tag_configure("launch", foreground="#7FFF00")
        self.log_text.tag_configure("normal", foreground=TEXT) 
        
        self.log_text.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        scroll_y=ttk.Scrollbar(self.log_card,orient="vertical",command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll_y.set); scroll_y.pack(side=tk.RIGHT,fill=tk.Y)
        self.log_card.pack(fill=tk.BOTH,expand=True)
        footer=ttk.Frame(root,style="InnerPlate.TFrame"); footer.pack(fill=tk.X,pady=(8,0))
        ttk.Label(footer,text="Use at your own risk. Ensure PX4 toolchain & Gazebo assets are installed.",style="Muted.TLabel").pack(anchor=tk.W)

        # --- ULG → KML ---
        kroot=ttk.Frame(self._kml_page,padding=0,style="InnerPlate.TFrame"); kroot.pack(fill=tk.BOTH,expand=True)
        ttk.Label(kroot,text="Convert PX4 .ulg flight logs to .kml (fallback draws a bright red route).",style="Muted.TLabel").pack(anchor=tk.W,pady=(0,12))
        kcard=ttk.Frame(kroot,padding=16,style="Card.TFrame"); kcard.pack(fill=tk.X)
        krow1=ttk.Frame(kcard,style="Card.TFrame"); krow1.pack(fill=tk.X,pady=(0,12))
        ttk.Label(krow1,text="ULG Log File",style="Card.TLabel").pack(side=tk.LEFT); self.ulg_path_var=tk.StringVar()
        ttk.Entry(krow1,textvariable=self.ulg_path_var,width=64).pack(side=tk.LEFT,padx=10,fill=tk.X,expand=True)
        self._mk_button(krow1, text="Browse", style="GlassGhost.TButton", sound="click",
                        command=self._select_ulg, side=tk.LEFT)
        krow2=ttk.Frame(kcard,style="Card.TFrame"); krow2.pack(fill=tk.X)
        ttk.Label(krow2,text="Output Folder",style="Card.TLabel").pack(side=tk.LEFT); self.out_dir_var=tk.StringVar(value=str(Path.home()/ "Documents"))
        self.out_dir_var.set(str(self.kml_out_last_dir)) # Set initial value from config default
        ttk.Entry(krow2,textvariable=self.out_dir_var,width=64).pack(side=tk.LEFT,padx=10,fill=tk.X,expand=True)
        self._mk_button(krow2, text="Choose", style="GlassGhost.TButton", sound="click",
                        command=self._select_out_dir, side=tk.LEFT)
        kctrl=ttk.Frame(kroot,padding=(0,12,0,12),style="InnerPlate.TFrame"); kctrl.pack(fill=tk.X)
        self.convert_btn=self._mk_button(kctrl, text="Convert ULG → KML", style="GlassPrimary.TButton", sound="start",
                                         command=self._convert_ulg_to_kml, side=tk.LEFT)
        self.open_out_btn=self._mk_button(kctrl, text="Open Output Folder", style="GlassSecondary.TButton", sound="click",
                                          command=self._open_output_folder, side=tk.LEFT, padx=(10,0))
        self.k_status_var=tk.StringVar(value="Ready"); ttk.Label(kroot,textvariable=self.k_status_var,style="Muted.TLabel").pack(anchor=tk.W,pady=(6,0))

        # Show Simulation first
        self._sim_page.pack(fill=tk.BOTH,expand=True)

    def _switch_page(self, which:str):
        self._sim_page.pack_forget()
        self._kml_page.pack_forget()
        if which=="sim":
            self._seg_sim_btn.configure(style="SegmentActive.TButton")
            self._seg_kml_btn.configure(style="Segment.TButton")
            self._sim_page.pack(fill=tk.BOTH,expand=True)
            try: play_sound("info", widget=self, loud=True)
            except Exception: pass
        else:
            self._seg_sim_btn.configure(style="Segment.TButton")
            self._seg_kml_btn.configure(style="SegmentActive.TButton")
            self._kml_page.pack(fill=tk.BOTH,expand=True)
            try: play_sound("info", widget=self, loud=True)
            except Exception: pass

    # -------- File/Dir selection (Zenity preferred; fixed filters) --------
    def _select_px4_dir(self):
        d=None
        
        initial_dir = self.px4_dir_var.get() if Path(self.px4_dir_var.get()).is_dir() else str(Path.home())
        
        if self._zenity_available():
            try:
                # Use initial_dir for Zenity
                d=subprocess.check_output(
                    ["zenity","--file-selection","--directory","--title","Select PX4 Firmware folder (contains 'Makefile')",
                     f"--filename={initial_dir}/"],
                    stderr=subprocess.DEVNULL, text=True
                ).strip() or None
            except subprocess.CalledProcessError:
                d=None
        else:
            # Use initialdir for Tkinter filedialog
            d=filedialog.askdirectory(title="Select PX4 Firmware folder (contains 'Makefile')", initialdir=initial_dir)
        if d:
            self.px4_dir_var.set(d)
            targets = self._get_vehicle_targets(d)
            self.vehicle_combo.configure(values=targets)
            if not self.vehicle_var.get() in targets and targets:
                self.vehicle_var.set(targets[0])
            try: play_sound("success", widget=self, loud=True)
            except Exception: pass

    def _import_coords(self):
        p=None
        # Use the PX4 directory as the initial location for plan/kml import
        initial_file = self.px4_dir_var.get() if Path(self.px4_dir_var.get()).is_dir() else str(Path.home())

        if self._zenity_available():
            try:
                p=subprocess.check_output(
                    ["zenity","--file-selection","--title","Select QGroundControl plan or KML",
                     f"--file-filter=Plan/KML | *.plan *.kml",
                     f"--file-filter=All files | *",
                     f"--filename={initial_file}/"], # Use filename for initial dir/file
                    stderr=subprocess.DEVNULL, text=True
                ).strip() or None
            except subprocess.CalledProcessError:
                p=None
        else:
            p=filedialog.askopenfilename(title="Select QGroundControl .plan or .kml file",
                                         filetypes=[("QGroundControl Plan","*.plan"),("KML File","*.kml"),("All files","*.*")],
                                         initialdir=initial_file)
        if not p: return
        fp=Path(p); lat=lon=None
        try:
            if fp.suffix.lower()==".kml": lat,lon=self._coords_from_kml(fp)
            elif fp.suffix.lower()==".plan": lat,lon=self._coords_from_plan(fp)
            if lat is None or lon is None: 
                play_sound("error", widget=self, loud=True); messagebox.showwarning("Not found","No suitable coordinates found."); return
        except Exception as e:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Import failed",f"Could not read coordinates: {e}"); return
        if lat<lon:  # simple anti-swapping heuristic
            lat,lon=lon,lat
            self._append_log("[INFO] Coordinates automatically swapped (lat assumed > lon).\n")
        self.lat_var.set(f"{lat:.8f}"); self.lon_var.set(f"{lon:.8f}")
        try: play_sound("success", widget=self, loud=True)
        except Exception: pass
        self._append_log(f"[INFO] Imported coordinates from {fp.name}: lat={lat:.8f}, lon={lon:.8f}\n")
        play_sound("info", widget=self, loud=True); messagebox.showinfo("Imported", f"Latitude: {lat:.6f}\nLongitude: {lon:.6f}")

    def _select_ulg(self):
        p=None
        
        # Use the last-used ULG directory
        initial_dir = str(self.ulg_last_dir)
        
        if self._zenity_available():
            try:
                p=subprocess.check_output(
                    ["zenity","--file-selection","--title","Select ULog file",
                     f"--file-filter=ULog | *.ulg",
                     f"--file-filter=All files | *",
                     f"--filename={initial_dir}/"],
                    stderr=subprocess.DEVNULL, text=True
                ).strip() or None
            except subprocess.CalledProcessError:
                p=None
        else:
            p=filedialog.askopenfilename(title="Select ULG log file",filetypes=[("PX4 ULog","*.ulg"),("All files","*.*")],
                                         initialdir=initial_dir)
        if p:
            self.ulg_path_var.set(p)
            # Save the directory of the selected file
            self.ulg_last_dir = Path(p).parent
            try: play_sound("success", widget=self, loud=True)
            except Exception: pass

    def _select_out_dir(self):
        d=None
        
        # Use the last-used KML output directory
        initial_dir = str(self.kml_out_last_dir)
        
        if self._zenity_available():
            try:
                d=subprocess.check_output(
                    ["zenity","--file-selection","--directory","--title","Select output folder for KML",
                     f"--filename={initial_dir}/"],
                    stderr=subprocess.DEVNULL, text=True
                ).strip() or None
            except subprocess.CalledProcessError:
                d=None
        else:
            d=filedialog.askdirectory(title="Select output folder for KML",
                                      initialdir=initial_dir)
        if d:
            self.out_dir_var.set(d)
            # Save the newly selected directory
            self.kml_out_last_dir = Path(d)
            try: play_sound("success", widget=self, loud=True)
            except Exception: pass

    def _coords_from_kml(self, file_path:Path):
        ns={"kml":"http://www.opengis.net/kml/2.2"}; root=ET.parse(str(file_path)).getroot()
        pt=root.find(".//kml:Point",ns)
        if pt is None: return (None,None)
        el=pt.find("kml:coordinates",ns)
        if el is None or not el.text: return (None,None)
        first=el.text.strip().split()[0]
        try:
            lo,la,*_=first.split(","); return (float(la), float(lo))
        except Exception: return (None,None)

    def _coords_from_plan(self, file_path:Path):
        data=json.loads(file_path.read_text())
        try:
            for it in data.get("mission",{}).get("items",[]):
                if "param5" in it and "param6" in it:
                    return (float(it["param5"]), float(it["param6"]))  # first waypoint
        except Exception: pass
        try:
            php=data.get("mission",{}).get("plannedHomePosition")
            if isinstance(php,list) and len(php)>=2:
                return (float(php[0]), float(php[1]))
        except Exception: pass
        return (None,None)

    # -------- Simulation --------
    def _start(self):
        if self.proc is not None: messagebox.showwarning("Already running","A simulation is already running."); return
        px4_dir=self.px4_dir_var.get().strip()
        lat=self.lat_var.get().strip(); lon=self.lon_var.get().strip()
        speed=self.speed_var.get().strip() or "20"
        vehicle=self.vehicle_var.get().strip() or "gazebo_typhoon_h480"
        alt=self.alt_var.get().strip() or "0"
        
        # Save PX4 directory immediately
        if px4_dir:
            self.px4_dir_var.set(px4_dir)
        
        if not px4_dir or not Path(px4_dir).is_dir():
            play_sound("error", widget=self, loud=True); messagebox.showerror("Missing folder","Please select a valid PX4 Firmware folder."); return
        try:
            lat_f=float(lat); lon_f=float(lon); assert -90<=lat_f<=90 and -180<=lon_f<=180
        except Exception:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Invalid location","Enter numeric latitude (-90..90) and longitude (-180..180) or import from .plan."); return
        try:
            speed_i=int(float(speed)); assert speed_i>0
        except Exception:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Invalid speed","Simulation speed must be a positive number."); return
        try:
            alt_f=float(alt)
        except Exception:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Invalid altitude","Home altitude must be a number (meters AMSL)."); return

        # Ensure output dir variable is updated before saving config
        out_dir = self.out_dir_var.get().strip()
        if out_dir:
            self.kml_out_last_dir = Path(out_dir)

        # Save all current configuration parameters
        self._save_config({"px4_dir":px4_dir,"lat":str(lat_f),"lon":str(lon_f),"speed":str(speed_i),"vehicle":vehicle, "alt":str(alt_f),
                           "ulg_last_dir": str(self.ulg_last_dir), "kml_out_last_dir": str(self.kml_out_last_dir)})

        setup_gz=os.path.join(px4_dir,"Tools","simulation","gazebo-classic","sitl_gazebo-classic","setup_gazebo.bash")
        bash=f'''
set -e
[ -f /etc/profile ] && source /etc/profile || true
[ -f "$HOME/.profile" ] && source "$HOME/.profile" || true
[ -f "$HOME/.bashrc" ] && source "$HOME/.bashrc" || true
[ -f /usr/share/gazebo/setup.sh ] && source /usr/share/gazebo/setup.sh || true
if [ -f "{setup_gz}" ]; then
  export PX4_BUILD_DIR="{px4_dir}/build/px4_sitl_default"
  source "{setup_gz}" "{px4_dir}" "$PX4_BUILD_DIR" || true
fi
export LIBGL_ALWAYS_SOFTWARE=1
export QT_QPA_PLATFORM=offscreen
export HOME="${{HOME:-$HOME}}"
export XDG_RUNTIME_DIR="${{XDG_RUNTIME_DIR:-/run/user/$(id -u)}}"
export GAZEBO_MASTER_URI="http://127.0.0.1:11345"
export HEADLESS=1
export PX4_HOME_LAT="{lat_f}"
export PX4_HOME_LON="{lon_f}"
export PX4_HOME_ALT="{alt_f}"
export PX4_SIM_SPEED_FACTOR="{speed_i}"
cd "{px4_dir}"
echo "[LAUNCH] env OK; starting: make px4_sitl_default {vehicle}"
make px4_sitl_default {vehicle}
'''
        try:
            self._stop_reader.clear()
            self.proc=subprocess.Popen(["/bin/bash","-lc",bash],cwd=px4_dir,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,universal_newlines=True)
            self._start_reader(self.proc.stdout)
            self._append_log(f"[INFO] Starting sim at lat={lat_f}, lon={lon_f}, alt={alt_f} m, speed={speed_i}, vehicle={vehicle}\n")
            self._append_log("[INFO] Sourced Gazebo classic + PX4 setup; headless GL enabled.\n")
            self._set_controls(True)
            play_sound("start", widget=self, loud=True)
        except FileNotFoundError:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Missing toolchain","'make' not found. Install: sudo apt-get install -y build-essential")
        except Exception as e:
            play_sound("error", widget=self, loud=True); messagebox.showerror("Failed to start", str(e))

    def _stop(self):
        if self.proc is None: return
        try: self.proc.terminate(); self.proc.wait(timeout=5)
        except Exception:
            try: self.proc.kill()
            except Exception: pass
        finally:
            self.proc=None; self._stop_reader.set(); self._set_controls(False)
            self._append_log("[INFO] Simulation stopped.\n"); play_sound("stop", widget=self, loud=True)

    def _set_controls(self, running:bool):
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    # -------- Logs (Color-Coded) --------
    def _toggle_logs(self):
        self._log_visible=not self._log_visible
        if self._log_visible:
            self.toggle_logs_btn.configure(text="Hide Logs"); self.log_card.pack(fill=tk.BOTH,expand=True)
            try: play_sound("info", widget=self, loud=True)
            except Exception: pass
        else:
            self.toggle_logs_btn.configure(text="Show Logs"); self.log_card.pack_forget()
            try: play_sound("info", widget=self, loud=True)
            except Exception: pass

    def _start_reader(self, pipe):
        def reader():
            for line in iter(pipe.readline,""):
                if self._stop_reader.is_set(): break
                self.log_queue.put(line)
            try: pipe.close()
            except Exception: pass
        threading.Thread(target=reader, daemon=True).start()

    def _poll_log_queue(self):
        try:
            while True:
                line=self.log_queue.get_nowait()
                if self._log_visible: self._append_log(line)
        except queue.Empty: pass
        self.after(80, self._poll_log_queue)

    def _append_log(self, text:str):
        # Determine tag based on content for color-coding
        tag = "normal"
        if "[LAUNCH]" in text or "[INFO] Starting sim" in text:
            tag = "launch"
        elif "[ERROR]" in text or "fail" in text.lower() or "error" in text.lower():
            tag = "error"
        elif "[INFO]" in text or "[INSTALL]" in text:
            tag = "info"
            
        self.log_text.insert(tk.END, text, tag); 
        self.log_text.see(tk.END)

    # -------- KML Converter --------
    def _open_output_folder(self):
        out=self.out_dir_var.get().strip()
        if out:
            try:
                subprocess.Popen(["xdg-open",out])
            except Exception: pass

    def _unique_name(self, base:Path)->Path:
        if not base.exists(): return base
        stem,suf=base.stem, base.suffix; i=1
        while True:
            cand=base.with_name(f"{stem}-{i}{suf}")
            if not cand.exists(): return cand
            i+=1

    def _ensure_kml_runtime(self):
        def log(s): self._append_log(s)
        return _ensure_import("pyulog",PY_DEPS["pyulog"],log) and _ensure_import("simplekml",PY_DEPS["simplekml"],log)

    def _convert_ulg_to_kml(self):
        ulg=self.ulg_path_var.get().strip(); out_dir=self.out_dir_var.get().strip()
        if not ulg or not Path(ulg).is_file():
            play_sound("error", widget=self, loud=True); messagebox.showerror("Missing ULG","Select a valid .ulg file."); return
        if not out_dir or not Path(out_dir).is_dir():
            play_sound("error", widget=self, loud=True); messagebox.showerror("Missing output folder","Select a valid output folder."); return
        if not self._ensure_kml_runtime():
            play_sound("error", widget=self, loud=True); self.k_status_var.set("Could not install pyulog/simplekml")
            messagebox.showerror("ULG → KML","Could not install required Python packages (pyulog/simplekml)."); return

        from shutil import which
        cmd=["ulog2kml", ulg] if which("ulog2kml") else [sys.executable,"-m","pyulog.ulog2kml", ulg]
        self.k_status_var.set("Converting…"); self.convert_btn.configure(state=tk.DISABLED)
        
        # Ensure output dir variable is updated before saving config
        self.kml_out_last_dir = Path(out_dir)
        
        def run():
            try:
                p=subprocess.run(cmd,cwd=out_dir,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                if p.returncode==0 and (Path(out_dir)/"track.kml").exists():
                    produced=Path(out_dir)/"track.kml"
                    tgt=self._unique_name(Path(out_dir)/(Path(ulg).stem+".kml"))
                    try: produced.rename(tgt)
                    except Exception:
                        data=produced.read_bytes(); tgt.write_bytes(data)
                        try: produced.unlink()
                        except Exception: pass
                    self._set_k_status(f"KML created: {tgt.name}",ok=True); play_sound("success", widget=self, loud=True); return
                
                # Fallback to internal converter
                self._append_log("[INFO] ulog2kml failed; running fallback converter...\n")
                tgt=self._unique_name(Path(out_dir)/(Path(ulg).stem+".kml"))
                _fallback_ulog_to_kml(ulg,str(tgt))
                self._set_k_status(f"KML created (fallback): {tgt.name}",ok=True); play_sound("success", widget=self, loud=True)
            except Exception as e:
                self._set_k_status(f"Conversion error: {e}",ok=False); play_sound("error", widget=self, loud=True)
            finally:
                try: self.convert_btn.configure(state=tk.NORMAL)
                except Exception: pass
                
        threading.Thread(target=run,daemon=True).start()

    def _set_k_status(self,text,ok=True):
        self.k_status_var.set(text)
        try: (messagebox.showinfo if ok else messagebox.showerror)("ULG → KML", text)
        except Exception: pass

    # -------- Config & Close --------
    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                d=json.loads(CONFIG_PATH.read_text())
                
                px4_dir = d.get("px4_dir","")
                self.px4_dir_var.set(px4_dir)
                self.lat_var.set(d.get("lat",""))
                self.lon_var.set(d.get("lon",""))
                self.speed_var.set(d.get("speed","20"))
                self.alt_var.set(d.get("alt","0")) 

                # Load last used directories (NEW)
                self.ulg_last_dir = Path(d.get("ulg_last_dir", str(Path.home())))
                self.kml_out_last_dir = Path(d.get("kml_out_last_dir", str(Path.home() / "Documents")))
                self.out_dir_var.set(str(self.kml_out_last_dir))
                
                # Update vehicle targets on load
                targets = self._get_vehicle_targets(px4_dir)
                self.vehicle_combo.configure(values=targets)
                if self.vehicle_var.get() not in targets:
                    self.vehicle_var.set(d.get("vehicle", targets[0] if targets else "gazebo_typhoon_h480"))
                
            except Exception: pass
            
    def _save_config(self,data:dict):
        # Add the last used directories to the data dictionary before saving
        data["ulg_last_dir"] = str(self.ulg_last_dir)
        data["kml_out_last_dir"] = str(self.kml_out_last_dir)
        try: CONFIG_PATH.write_text(json.dumps(data,indent=2))
        except Exception: pass
        
    def _on_close(self):
        if self.proc is not None and not messagebox.askyesno("Quit?","A simulation is running. Stop and quit?"): return
        if self.proc is not None: self._stop()
        
        # Save config on close to preserve final directory states
        current_config = {
            "px4_dir": self.px4_dir_var.get(),
            "lat": self.lat_var.get(),
            "lon": self.lon_var.get(),
            "speed": self.speed_var.get(),
            "vehicle": self.vehicle_var.get(),
            "alt": self.alt_var.get()
        }
        self._save_config(current_config)

        self.destroy()

def main():
    app=PX4SimApp(); app.mainloop()

if __name__=="__main__":
    main()
