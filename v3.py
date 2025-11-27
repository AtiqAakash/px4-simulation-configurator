#!/usr/bin/env python3
"""
Beagle Sim — Premium Edition (Ubuntu GUI)

Features:
- Backend: Docker Compose + Redis (No local PX4 build required).
- UI: Premium Dark Theme, Glass effects, Native Dialogs.
- Audio: Distinct Ubuntu system sounds.
- Logic: Auto-fix Lat/Lon, Factory Sync Countdown, BGC Auto-restart.
- Tools: Uses LOCAL pyulog + AUTO-INSTALLS missing dependencies.
- System: Auto-registers .desktop file to fix Taskbar Icon.
- Display: FIXED SIZE 1500x1220 (Maximization removed).
"""

import json, os, queue, subprocess, threading, webbrowser, xml.etree.ElementTree as ET, sys, shutil, math, io, urllib.request, signal, time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Beagle Sim"
CONFIG_PATH = Path.home() / ".beagle_docker_config.json"
CACHE_DIR = Path.home() / ".cache"
AVATAR_URL = "https://atiq.no/about-photo.jpg"
AVATAR_CACHE = CACHE_DIR / "beagle_sim_photo.png"
DEFAULT_PROJECT_DIR = str(Path.home() / "Development/releases")
BGC_DESKTOP_FILE = Path.home() / "Desktop/BeagleGroundControl.desktop"

# --- CONFIGURATION: LOCAL TOOLS ---
LOCAL_PYULOG_ROOT = Path.home() / "Music/pyulog"

# ---------------- Theme ----------------
# Accents from "Option C" (bright green), BACKGROUND from older navy theme
ACCENT        = "#A8E063"   # bright willow green
ACCENT_HOVER  = "#99D554"
ACCENT_DEEP   = "#7ABD36"
SECONDARY     = "#9aa6b2"
SECONDARY_HOVER = "#8d99a6"

# Background & cards from the blue/navy theme
BG         = "#0a0e14"
GLASS_BG   = "#0e1620"
GLASS_IN   = "#121c29"
GLASS_EDGE = "#26384f"

CARD       = "#111827"
CARD_ALT   = "#0e1620"
BORDER     = "#1e2733"

TEXT  = "#e9f1fb"
MUTED = "#9aa6b2"

DANGER   = "#ef4444"
DANGER_H = "#dc2626"
SUCCESS  = "#2eff7b"

# ---------------- Helper: Docker Command ----------------
def get_docker_cmd():
    if shutil.which("docker-compose"):
        return "docker-compose"
    return "docker compose"

DOCKER_CMD = get_docker_cmd()

# ---------------- Dependency Manager ----------------
def install_deps(packages, log_fn=None):
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages"] + packages
    if log_fn:
        log_fn(f"[INSTALL] Installing dependencies: {', '.join(packages)}...\n")
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if log_fn:
            log_fn("[INSTALL] Success. Dependencies installed.\n")
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"[ERROR] Install failed: {e}\n")
        return False

# ---------------- Sounds ----------------
def play_sound(kind: str, widget: tk.Misc | None = None, *, loud: bool = True):
    ids = {
        "click": "button-pressed",
        "start": "bell",
        "success": "message-new-instant",
        "stop": "message-new-email",
        "error": "dialog-error",
        "info": "dialog-information",
    }
    sid = ids.get(kind, "dialog-information")
    file_map = {
        "click": "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",
        "start": "/usr/share/sounds/freedesktop/stereo/bell.oga",
        "success": "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
        "stop": "/usr/share/sounds/freedesktop/stereo/message-new-email.oga",
        "error": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
        "info": "/usr/share/sounds/freedesktop/stereo/dialog-information.oga",
    }
    file_path = file_map.get(kind)
    canberra = shutil.which("canberra-gtk-play")
    if canberra:
        try:
            subprocess.Popen([canberra, "--id", sid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if loud:
                subprocess.Popen([canberra, "--id", sid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    if file_path and Path(file_path).exists():
        paplay = shutil.which("paplay")
        if paplay:
            try:
                subprocess.Popen(
                    [paplay, "--volume", "98304", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass
    try:
        if widget is not None:
            widget.bell()
            if loud:
                widget.after(40, lambda: widget.bell())
    except Exception:
        pass

# ---------------- GUI Base ----------------
class ThemedApp(tk.Tk):
    def __init__(self):
        super().__init__(className="beagle-sim")
        # CRITICAL FOR TASKBAR ICON: Set WM Class
        try:
            self.wm_class("beagle-sim", "beagle-sim")
        except Exception:
            pass
        try:
            self.call("tk", "appname", APP_TITLE)
            self.call("wm", "iconname", ".", APP_TITLE)
        except Exception:
            pass

        self.title(APP_TITLE)

        # --- FIXED SIZE LOGIC ---
        self.geometry("1500x1220")
        self.resizable(False, False)
        self.configure(bg=BG)

        self._style()
        self._load_icon()
        self._ensure_desktop_file()

    def _load_icon(self):
        try:
            from tkinter import PhotoImage
            script_dir = Path(__file__).parent
            candidates = [
                script_dir / "beagle-sim-256.png",
                script_dir / "beagle-sim-128.png",
                "/usr/share/icons/hicolor/256x256/apps/beagle-sim.png",
            ]
            for p in candidates:
                if p.exists():
                    self._app_icon = PhotoImage(file=str(p))
                    self.iconphoto(True, self._app_icon)
                    break
        except Exception:
            pass

    def _ensure_desktop_file(self):
        """Auto-generates a .desktop file so the Taskbar Icon works on Ubuntu"""
        try:
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_file = desktop_dir / "beagle-sim.desktop"

            script_path = Path(__file__).resolve()
            icon_path = script_path.parent / "beagle-sim-256.png"
            if not icon_path.exists():
                icon_path = script_path.parent / "beagle.png"

            content = f"""[Desktop Entry]
Name={APP_TITLE}
Comment=Containerized Drone Simulator
Exec="{sys.executable}" "{script_path}"
Icon={icon_path}
Terminal=false
Type=Application
StartupWMClass=beagle-sim
Categories=Development;Utility;
"""
            if not desktop_file.exists() or desktop_file.read_text().strip() != content.strip():
                desktop_file.write_text(content)
                desktop_file.chmod(0o755)
                subprocess.run(
                    ["update-desktop-database", str(desktop_dir)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        # Frames
        s.configure("TFrame", background=BG)
        s.configure("Backplate.TFrame", background=GLASS_BG, relief="flat")
        s.configure("InnerPlate.TFrame", background=GLASS_IN, relief="flat")
        s.configure("Card.TFrame", background=CARD, relief="flat")
        s.configure("CardAlt.TFrame", background=CARD_ALT, relief="flat")

        # Labels
        s.configure("TLabel", background=BG, foreground=TEXT, font=("DejaVu Sans", 11))
        s.configure("Card.TLabel", background=CARD, foreground=TEXT, font=("DejaVu Sans", 11))
        s.configure("Header.TLabel", background=CARD_ALT, foreground=TEXT, font=("DejaVu Sans Medium", 14))
        s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("DejaVu Sans", 11))
        s.configure("Title.TLabel", background=CARD_ALT, foreground=ACCENT, font=("DejaVu Sans Bold", 30))

        # Entries
        s.configure(
            "TEntry",
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            insertcolor=ACCENT,
            padding=6,
        )
        s.map("TEntry", bordercolor=[("focus", ACCENT)])

        # Combobox
        s.configure(
            "Beagle.TCombobox",
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=4,
        )
        s.map(
            "Beagle.TCombobox",
            fieldbackground=[("readonly", CARD), ("!disabled", CARD)],
            foreground=[("readonly", TEXT), ("!disabled", TEXT)],
            selectbackground=[("!disabled", CARD)],
            selectforeground=[("!disabled", TEXT)],
        )

        # Primary Button
        s.configure(
            "GlassPrimary.TButton",
            background=ACCENT,
            foreground="#061018",
            bordercolor="#5cc0ff",
            darkcolor=ACCENT_DEEP,
            lightcolor="#9bd7ff",
            relief="flat",
            padding=[18, 12],
            font=("DejaVu Sans Medium", 12),
        )
        s.map(
            "GlassPrimary.TButton",
            background=[("active", ACCENT_HOVER), ("pressed", ACCENT_DEEP)],
            bordercolor=[("focus", "#bfe7ff")],
        )

        # Secondary Button
        s.configure(
            "GlassSecondary.TButton",
            background=SECONDARY,
            foreground="#0f141a",
            bordercolor="#b9c2cb",
            darkcolor="#707b86",
            lightcolor="#cdd5dd",
            relief="flat",
            padding=[16, 12],
            font=("DejaVu Sans Medium", 12),
        )
        s.map(
            "GlassSecondary.TButton",
            background=[("active", SECONDARY_HOVER)],
            bordercolor=[("focus", "#e2e8f0")],
        )

        # Ghost Button
        s.configure(
            "GlassGhost.TButton",
            background=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            relief="groove",
            padding=[14, 10],
            font=("DejaVu Sans Medium", 11),
        )
        s.map(
            "GlassGhost.TButton",
            background=[("active", "#162231")],
            bordercolor=[("active", ACCENT), ("focus", ACCENT)],
        )

        # Danger Button
        s.configure(
            "GlassDanger.TButton",
            background=DANGER,
            foreground="#FFFFFF",
            bordercolor="#ff8a8a",
            darkcolor="#7a1b1b",
            lightcolor="#ffb3b3",
            relief="flat",
            padding=[18, 12],
            font=("DejaVu Sans Medium", 12),
        )
        s.map(
            "GlassDanger.TButton",
            background=[("active", DANGER_H)],
            foreground=[("!disabled", "#FFFFFF"), ("active", "#FFFFFF"), ("disabled", "#FFFFFF")],
        )

        # Segment Buttons
        s.configure(
            "Segment.TButton",
            background=GLASS_IN,
            foreground=TEXT,
            bordercolor=GLASS_EDGE,
            relief="flat",
            padding=[24, 14],
            font=("DejaVu Sans Medium", 13),
        )
        s.map(
            "Segment.TButton",
            background=[("active", "#152131")],
            bordercolor=[("focus", ACCENT)],
        )
        s.configure(
            "SegmentActive.TButton",
            background=ACCENT,
            foreground="#061018",
            bordercolor="#bfe7ff",
            relief="flat",
            padding=[24, 14],
            font=("DejaVu Sans Bold", 13),
        )

        # Checkbox & Progress
        s.configure(
            "TCheckbutton",
            background=CARD,
            foreground=TEXT,
            font=("DejaVu Sans", 11),
            indicatorcolor=CARD,
            indicatorrelief="flat",
        )
        s.map(
            "TCheckbutton",
            indicatorcolor=[("selected", ACCENT)],
            foreground=[("active", ACCENT)],
        )
        s.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=GLASS_IN,
            bordercolor=BG,
            thickness=6,
        )

        # Text defaults
        self.option_add("*Text.background", CARD)
        self.option_add("*Text.foreground", TEXT)
        self.option_add("*Text.insertBackground", ACCENT)
        self.option_add("*Text.selectBackground", ACCENT)


# ---------------- App ----------------
class PX4SimApp(ThemedApp):
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.log_queue = queue.Queue()
        self.ulg_last_dir = Path.home()
        self.kml_out_last_dir = Path.home() / "Documents"
        self.compose_file = "docker-compose.simulation.yml"
        self._log_visible = True

        # Splash state
        self._splash = None
        self._splash_canvas = None
        self._splash_drone_id = None
        self._splash_img = None
        self._splash_prog_bg = None
        self._splash_prog_fg = None
        self._splash_title_id = None
        self._splash_step = 0

        self._build_ui()
        self._load_config()
        self._poll_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start with main window hidden, show splash first
        self.withdraw()
        self.after(10, self._show_startup_animation)

    def _mk_button(self, parent, *, text, style, sound="click", command=None, **pack_kwargs):
        def invoke():
            play_sound(sound, widget=self, loud=True)
            if command:
                command()
        btn = ttk.Button(parent, text=text, style=style, command=invoke)
        btn.bind("<Button-1>", lambda e: play_sound(sound, widget=self, loud=True), add="+")
        btn.bind("<Key-Return>", lambda e: (play_sound(sound, widget=self, loud=True), invoke()), add="+")
        btn.bind("<Key-space>", lambda e: (play_sound(sound, widget=self, loud=True), invoke()), add="+")
        btn.pack(**pack_kwargs)
        return btn

    def _load_pillow(self):
        try:
            from PIL import Image, ImageTk, ImageDraw
            return Image, ImageTk, ImageDraw
        except ImportError:
            return None, None, None

    def _load_beagle_logo(self):
        Image, ImageTk, _ = self._load_pillow()
        if not Image:
            return None
        script_dir = Path(__file__).parent
        for lp in (str(script_dir / "beagle.png"), "/opt/beagle-sim/beagle.png"):
            p = Path(lp)
            if p.exists():
                try:
                    img = Image.open(lp).convert("RGBA")
                    base_h = int(64 * 1.25)
                    w, h = img.size
                    if h > 0:
                        img = img.resize((max(1, int(w * (base_h / h))), base_h), Image.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except Exception:
                    return None
        return None

    def _get_circle_avatar(self, url: str, size: int = 40):
        Image, ImageTk, ImageDraw = self._load_pillow()
        if not Image:
            return None
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if not AVATAR_CACHE.exists():
                with urllib.request.urlopen(url, timeout=8) as r:
                    AVATAR_CACHE.write_bytes(r.read())
            raw = AVATAR_CACHE.read_bytes()
            img = Image.open(io.BytesIO(raw)).convert("RGBA").resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            d = ImageDraw.Draw(mask)
            d.ellipse((0, 0, size, size), fill=255)
            img.putalpha(mask)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _load_drone_png(self):
        """Load VTOL drone PNG for splash animation."""
        Image, ImageTk, _ = self._load_pillow()
        if not Image:
            return None
        script_dir = Path(__file__).parent
        candidates = [
            script_dir / "vtol_drone.png",
            script_dir / "drone.png",
            script_dir / "beagle.png",
        ]
        for p in candidates:
            if p.exists():
                try:
                    img = Image.open(p).convert("RGBA")
                    # Scale to a nice size for 1440x720 splash
                    # ↓ 10% smaller than before
                    target_h = int(260 * 0.9)
                    w, h = img.size
                    if h > 0:
                        img = img.resize((max(1, int(w * (target_h / h))), target_h), Image.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except Exception:
                    return None
        return None

    def _zenity_available(self) -> bool:
        return shutil.which("zenity") is not None

    # ---------- Splash Animation ----------
    def _show_startup_animation(self):
        try:
            play_sound("start", widget=self)

            self._splash = tk.Toplevel(self)
            self._splash.overrideredirect(True)
            self._splash.attributes("-topmost", True)

            # Global window opacity ~90% (10% transparent)
            try:
                self._splash.attributes("-alpha", 0.9)
            except Exception:
                pass

            # Give splash same icon as main if available
            if hasattr(self, "_app_icon"):
                try:
                    self._splash.iconphoto(True, self._app_icon)
                except Exception:
                    pass

            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            # 1440x720 splash
            w, h = 1440, 720
            x = (sw - w) // 2
            y = (sh - h) // 2
            self._splash.geometry(f"{w}x{h}+{x}+{y}")

            # Use a special color as the transparent key
            transparent_key = "#010203"

            self._splash_canvas = tk.Canvas(
                self._splash,
                bg=transparent_key,
                bd=0,
                highlightthickness=0,
                relief="flat",
            )
            self._splash_canvas.pack(fill="both", expand=True)

            # Try to make that color fully transparent (if WM supports it)
            try:
                self._splash.attributes("-transparentcolor", transparent_key)
            except Exception:
                # If unsupported, it will just show a dark-ish background
                pass

            drone_img = self._load_drone_png()
            if drone_img is not None:
                self._splash_img = drone_img
                start_x = -250
                start_y = h // 2
                self._splash_drone_id = self._splash_canvas.create_image(
                    start_x, start_y, image=self._splash_img
                )
            else:
                # Fallback simple shape
                self._splash_drone_id = self._splash_canvas.create_polygon(
                    0, h // 2,
                    100, h // 2 - 30,
                    100, h // 2 + 30,
                    fill=ACCENT,
                    outline=ACCENT_DEEP,
                    width=2,
                )

            # Main title - moved a bit higher (was h//2 - 120)
            self._splash_title_id = self._splash_canvas.create_text(
                w // 2,
                h // 2 - 200,
                text="Beagle Sim",
                fill=ACCENT,
                font=("DejaVu Sans Bold", 32),
            )

            # Bottom text
            self._splash_canvas.create_text(
                w // 2,
                h - 80,
                text="Developed by Atiq",
                fill="#9aa6b2",
                font=("DejaVu Sans", 14),
            )

            # Slim progress bar floating at the bottom
            self._splash_prog_bg = self._splash_canvas.create_rectangle(
                w // 2 - 180,
                h - 55,
                w // 2 + 180,
                h - 50,
                fill="#1b2533",
                outline="",
            )
            self._splash_prog_fg = self._splash_canvas.create_rectangle(
                w // 2 - 180,
                h - 55,
                w // 2 - 180,
                h - 50,
                fill=ACCENT,
                outline="",
            )

            self._splash_step = 0
            self._animate_splash()
        except Exception:
            # If splash fails, just show main window
            self.deiconify()
            self.lift()
            try:
                self.focus_force()
            except Exception:
                pass

    def _animate_splash(self):
        if self._splash is None or self._splash_canvas is None:
            return

        self._splash_step += 1
        # ~24–25 fps: 40 ms per frame, 90 frames -> ~3.6s total
        total_frames = 90

        w = 1440
        h = 720

        t = min(self._splash_step / total_frames, 1.0)

        # Start completely off-screen left, exit off-screen right
        start_x = -250
        end_x = w + 250
        x = start_x + (end_x - start_x) * t
        y = h // 2

        if isinstance(self._splash_drone_id, int):
            self._splash_canvas.coords(self._splash_drone_id, x, y)

        # Progress bar fill
        prog_len = 360 * t
        if self._splash_prog_fg is not None:
            self._splash_canvas.coords(
                self._splash_prog_fg,
                w // 2 - 180,
                h - 55,
                w // 2 - 180 + prog_len,
                h - 50,
            )

        if self._splash_step >= total_frames:
            self._splash.after(500, self._end_splash)
        else:
            self._splash.after(40, self._animate_splash)

    def _end_splash(self):
        try:
            if self._splash is not None:
                self._splash.destroy()
        except Exception:
            pass
        self._splash = None
        # Show main window
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass

    # ---------- Main UI ----------
    def _build_ui(self):
        header = ttk.Frame(self, padding=(24, 20), style="CardAlt.TFrame")
        header.pack(fill=tk.X)
        left = ttk.Frame(header, style="CardAlt.TFrame")
        left.pack(side=tk.LEFT, anchor="w")
        self._header_logo = self._load_beagle_logo()
        if self._header_logo:
            ttk.Label(left, image=self._header_logo, background=CARD_ALT).pack(side=tk.LEFT, padx=(0, 100))
        title_col = ttk.Frame(left, style="CardAlt.TFrame")
        title_col.pack(side=tk.LEFT)
        ttk.Label(title_col, text="Simulation Suit", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_col,
            text="Premium Edition V3",
            background=CARD_ALT,
            foreground=ACCENT,
        ).pack(anchor="w")

        right = ttk.Frame(header, style="CardAlt.TFrame")
        right.pack(side=tk.RIGHT, anchor="e")
        lab = ttk.Label(right, text="© Atiq", style="Header.TLabel", cursor="hand2")
        lab.pack(side=tk.LEFT, padx=(0, 10))
        self._avatar_img = self._get_circle_avatar(AVATAR_URL, size=40)
        if self._avatar_img:
            ava = ttk.Label(right, image=self._avatar_img, background=CARD_ALT, cursor="hand2")
            ava.pack(side=tk.LEFT)
        for ch in right.winfo_children():
            ch.bind(
                "<Button-1>",
                lambda e: (play_sound("info", widget=self, loud=True), webbrowser.open_new_tab("https://atiq.no")),
            )

        plate = ttk.Frame(self, padding=18, style="Backplate.TFrame")
        plate.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        segrow = ttk.Frame(plate, padding=8, style="InnerPlate.TFrame")
        segrow.pack(fill=tk.X, pady=(0, 10))
        self._sim_page = ttk.Frame(plate, padding=16, style="InnerPlate.TFrame")
        self._kml_page = ttk.Frame(plate, padding=16, style="InnerPlate.TFrame")

        self._seg_sim_btn = self._mk_button(
            segrow,
            text="Simulation Deck",
            style="SegmentActive.TButton",
            sound="click",
            command=lambda: self._switch_page("sim"),
            side=tk.LEFT,
            padx=(4, 6),
        )
        self._seg_kml_btn = self._mk_button(
            segrow,
            text="Log Converter",
            style="Segment.TButton",
            sound="click",
            command=lambda: self._switch_page("kml"),
            side=tk.LEFT,
            padx=(6, 4),
        )

        # --- Simulation UI ---
        root = ttk.Frame(self._sim_page, padding=0, style="InnerPlate.TFrame")
        root.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            root,
            text="Dockerized PX4 SITL + Redis Configuration.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))

        card = ttk.Frame(root, padding=16, style="Card.TFrame")
        card.pack(fill=tk.X, pady=(0, 12))

        # Project dir (hidden UI, but value stored)
        self.proj_dir_var = tk.StringVar(value=DEFAULT_PROJECT_DIR)

        r2 = ttk.Frame(card, style="Card.TFrame")
        r2.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(r2, text="Lat (°)", style="Card.TLabel").pack(side=tk.LEFT)
        self.lat_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.lat_var, width=14).pack(side=tk.LEFT, padx=(8, 10))
        ttk.Label(r2, text="Lon (°)", style="Card.TLabel").pack(side=tk.LEFT)
        self.lon_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.lon_var, width=14).pack(side=tk.LEFT, padx=(8, 10))

        self._mk_button(
            r2,
            text="Import Plan / KML",
            style="GlassSecondary.TButton",
            sound="click",
            command=self._import_coords,
            side=tk.LEFT,
            padx=(10, 0),
        )

        r3 = ttk.Frame(card, style="Card.TFrame")
        r3.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(r3, text="Speed (×)", style="Card.TLabel").pack(side=tk.LEFT)
        self.speed_var = tk.StringVar(value="20")
        ttk.Entry(r3, textvariable=self.speed_var, width=8).pack(side=tk.LEFT, padx=(8, 15))

        ttk.Label(r3, text="Alt (m)", style="Card.TLabel").pack(side=tk.LEFT)
        self.alt_var = tk.StringVar(value="0")
        ttk.Entry(r3, textvariable=self.alt_var, width=8).pack(side=tk.LEFT, padx=(8, 15))

        ttk.Label(r3, text="Model", style="Card.TLabel").pack(side=tk.LEFT)
        self.vehicle_var = tk.StringVar(value="octo_beagle")
        self.vehicle_combo = ttk.Combobox(
            r3,
            textvariable=self.vehicle_var,
            state="readonly",
            values=["octo_beagle", "beagle_m"],
            width=18,
            style="Beagle.TCombobox",
        )
        self.vehicle_combo.pack(side=tk.LEFT, padx=(8, 20))
        self.vehicle_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: play_sound("click", widget=self, loud=True),
            add="+",
        )

        r4 = ttk.Frame(card, style="Card.TFrame")
        r4.pack(fill=tk.X)
        self.restart_bgc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            r4,
            text="Auto-restart BeagleGroundControl",
            variable=self.restart_bgc_var,
            style="TCheckbutton",
        ).pack(side=tk.LEFT)

        ctrls = ttk.Frame(root, padding=(0, 12, 0, 12), style="InnerPlate.TFrame")
        ctrls.pack(fill=tk.X)
        self.start_btn = self._mk_button(
            ctrls,
            text="Start Simulation",
            style="GlassPrimary.TButton",
            sound="start",
            command=self._start,
            side=tk.LEFT,
        )
        self.stop_btn = self._mk_button(
            ctrls,
            text="Stop",
            style="GlassDanger.TButton",
            sound="stop",
            command=self._stop,
            side=tk.LEFT,
            padx=(10, 0),
        )
        self.stop_btn.configure(state=tk.DISABLED)

        self.status_frame = ttk.Frame(root, style="InnerPlate.TFrame")
        self.status_frame.pack(fill=tk.X, pady=(0, 10))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            self.status_frame,
            textvariable=self.status_var,
            style="Muted.TLabel",
            foreground=ACCENT,
        ).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(
            self.status_frame,
            orient=tk.HORIZONTAL,
            length=100,
            mode="determinate",
        )
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        self.log_card = ttk.Labelframe(
            root,
            text="System Logs",
            padding=10,
            style="Card.TFrame",
        )
        s = ttk.Style(self)
        s.configure("Card.TLabelframe", background=CARD, foreground=ACCENT)
        s.configure(
            "Card.TLabelframe.Label",
            background=CARD,
            foreground=ACCENT,
            font=("DejaVu Sans Medium", 13),
        )
        self.log_text = tk.Text(
            self.log_card,
            wrap=tk.NONE,
            height=12,
            bd=0,
            highlightthickness=0,
            background=CARD,
            foreground=TEXT,
            insertbackground=ACCENT,
        )
        self.log_text.tag_configure("info", foreground=ACCENT)
        self.log_text.tag_configure("error", foreground=DANGER)
        self.log_text.tag_configure("success", foreground=SUCCESS)
        self.log_text.tag_configure("launch", foreground="#7FFF00")
        self.log_text.tag_configure("normal", foreground=TEXT)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y = ttk.Scrollbar(self.log_card, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_card.pack(fill=tk.BOTH, expand=True)

        # --- ULG → KML ---
        kroot = ttk.Frame(self._kml_page, padding=0, style="InnerPlate.TFrame")
        kroot.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            kroot,
            text="Convert PX4 .ulg flight logs to .kml (fallback draws a bright red route).",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))
        kcard = ttk.Frame(kroot, padding=16, style="Card.TFrame")
        kcard.pack(fill=tk.X)
        krow1 = ttk.Frame(kcard, style="Card.TFrame")
        krow1.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(krow1, text="ULG Log File", style="Card.TLabel").pack(side=tk.LEFT)
        self.ulg_path_var = tk.StringVar()
        ttk.Entry(krow1, textvariable=self.ulg_path_var, width=64).pack(
            side=tk.LEFT, padx=10, fill=tk.X, expand=True
        )
        self._mk_button(
            krow1,
            text="Browse",
            style="GlassGhost.TButton",
            sound="click",
            command=self._select_ulg,
            side=tk.LEFT,
        )
        krow2 = ttk.Frame(kcard, style="Card.TFrame")
        krow2.pack(fill=tk.X)
        ttk.Label(krow2, text="Output Folder", style="Card.TLabel").pack(side=tk.LEFT)
        self.out_dir_var = tk.StringVar(value=str(Path.home() / "Documents"))
        self.out_dir_var.set(str(self.kml_out_last_dir))
        ttk.Entry(krow2, textvariable=self.out_dir_var, width=64).pack(
            side=tk.LEFT, padx=10, fill=tk.X, expand=True
        )
        self._mk_button(
            krow2,
            text="Choose",
            style="GlassGhost.TButton",
            sound="click",
            command=self._select_out_dir,
            side=tk.LEFT,
        )
        kctrl = ttk.Frame(kroot, padding=(0, 12, 0, 12), style="InnerPlate.TFrame")
        kctrl.pack(fill=tk.X)
        self.convert_btn = self._mk_button(
            kctrl,
            text="Convert ULG → KML",
            style="GlassPrimary.TButton",
            sound="start",
            command=self._convert_ulg_to_kml,
            side=tk.LEFT,
        )
        self.open_out_btn = self._mk_button(
            kctrl,
            text="Open Output Folder",
            style="GlassSecondary.TButton",
            sound="click",
            command=self._open_output_folder,
            side=tk.LEFT,
            padx=(10, 0),
        )
        self.k_status_var = tk.StringVar(value="Ready")
        ttk.Label(kroot, textvariable=self.k_status_var, style="Muted.TLabel").pack(
            anchor=tk.W, pady=(6, 0)
        )
        self._sim_page.pack(fill=tk.BOTH, expand=True)

    def _switch_page(self, which: str):
        self._sim_page.pack_forget()
        self._kml_page.pack_forget()
        if which == "sim":
            self._seg_sim_btn.configure(style="SegmentActive.TButton")
            self._seg_kml_btn.configure(style="Segment.TButton")
            self._sim_page.pack(fill=tk.BOTH, expand=True)
        else:
            self._seg_sim_btn.configure(style="Segment.TButton")
            self._seg_kml_btn.configure(style="SegmentActive.TButton")
            self._kml_page.pack(fill=tk.BOTH, expand=True)
        try:
            play_sound("info", widget=self, loud=True)
        except Exception:
            pass

    def _select_ulg(self):
        p = None
        initial_dir = str(self.ulg_last_dir)
        if self._zenity_available():
            try:
                p = (
                    subprocess.check_output(
                        [
                            "zenity",
                            "--file-selection",
                            "--title",
                            "Select ULog file",
                            "--file-filter=ULog | *.ulg",
                            "--file-filter=All files | *",
                            f"--filename={initial_dir}/",
                        ],
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                    .strip()
                    or None
                )
            except subprocess.CalledProcessError:
                p = None
        else:
            p = filedialog.askopenfilename(
                title="Select ULG log file",
                filetypes=[("PX4 ULog", "*.ulg"), ("All files", "*.*")],
                initialdir=initial_dir,
            )
        if p:
            self.ulg_path_var.set(p)
            self.ulg_last_dir = Path(p).parent
            try:
                play_sound("success", widget=self, loud=True)
            except Exception:
                pass

    def _select_out_dir(self):
        d = None
        initial_dir = str(self.kml_out_last_dir)
        if self._zenity_available():
            try:
                d = (
                    subprocess.check_output(
                        [
                            "zenity",
                            "--file-selection",
                            "--directory",
                            "--title",
                            "Select output folder",
                            f"--filename={initial_dir}/",
                        ],
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                    .strip()
                    or None
                )
            except subprocess.CalledProcessError:
                d = None
        else:
            d = filedialog.askdirectory(
                title="Select output folder for KML", initialdir=initial_dir
            )
        if d:
            self.out_dir_var.set(d)
            self.kml_out_last_dir = Path(d)
            try:
                play_sound("success", widget=self, loud=True)
            except Exception:
                pass

    def _coords_from_kml(self, file_path: Path):
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        root = ET.parse(str(file_path)).getroot()
        pt = root.find(".//kml:Point", ns)
        if pt is None:
            for elem in root.iter():
                if "coordinates" in elem.tag and elem.text:
                    parts = elem.text.strip().split(",")
                    if len(parts) >= 2:
                        return (float(parts[1]), float(parts[0]))
        if pt is None:
            return (None, None)
        el = pt.find("kml:coordinates", ns)
        if el is None or not el.text:
            return (None, None)
        first = el.text.strip().split()[0]
        try:
            lo, la, *_ = first.split(",")
            return (float(la), float(lo))
        except Exception:
            return (None, None)

    def _coords_from_plan(self, file_path: Path):
        data = json.loads(file_path.read_text())
        try:
            for it in data.get("mission", {}).get("items", []):
                if "param5" in it and "param6" in it:
                    return (float(it["param5"]), float(it["param6"]))
        except Exception:
            pass
        try:
            php = data.get("mission", {}).get("plannedHomePosition")
            if isinstance(php, list) and len(php) >= 2:
                return (float(php[0]), float(php[1]))
        except Exception:
            pass
        return (None, None)

    def _import_coords(self):
        p = None
        initial_file = (
            self.proj_dir_var.get()
            if Path(self.proj_dir_var.get()).is_dir()
            else str(Path.home())
        )
        if self._zenity_available():
            try:
                p = (
                    subprocess.check_output(
                        [
                            "zenity",
                            "--file-selection",
                            "--title",
                            "Select QGroundControl plan or KML",
                            "--file-filter=Plan/KML | *.plan *.kml",
                            "--file-filter=All files | *",
                            f"--filename={initial_file}/",
                        ],
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                    .strip()
                    or None
                )
            except subprocess.CalledProcessError:
                p = None
        else:
            p = filedialog.askopenfilename(
                title="Select QGroundControl .plan or .kml file",
                filetypes=[
                    ("QGroundControl Plan", "*.plan"),
                    ("KML File", "*.kml"),
                    ("All files", "*.*"),
                ],
                initialdir=initial_file,
            )
        if not p:
            return
        fp = Path(p)
        lat = lon = None
        try:
            if fp.suffix.lower() == ".kml":
                lat, lon = self._coords_from_kml(fp)
            elif fp.suffix.lower() == ".plan":
                lat, lon = self._coords_from_plan(fp)
            if lat is None or lon is None:
                play_sound("error", widget=self, loud=True)
                messagebox.showwarning("Not found", "No suitable coordinates found.")
                return
        except Exception as e:
            play_sound("error", widget=self, loud=True)
            messagebox.showerror("Import failed", f"Could not read coordinates: {e}")
            return

        # Auto-fix Somalia
        if lat < lon:
            lat, lon = lon, lat
            self._append_log("[INFO] Coordinates automatically swapped (lat assumed > lon).\n")

        self.lat_var.set(f"{lat:.8f}")
        self.lon_var.set(f"{lon:.8f}")
        try:
            play_sound("success", widget=self, loud=True)
        except Exception:
            pass
        self._append_log(
            f"[INFO] Imported coordinates from {fp.name}: lat={lat:.8f}, lon={lon:.8f}\n"
        )

    # -------- Simulation Logic (Docker) --------
    def _start(self):
        if self.is_running:
            messagebox.showwarning("Running", "Simulation is already running.")
            return

        proj_dir = self.proj_dir_var.get().strip()
        if not proj_dir or not Path(proj_dir).is_dir():
            play_sound("error", widget=self)
            messagebox.showerror("Error", "Invalid Docker Project Folder.")
            return

        try:
            lat = self.lat_var.get().replace(",", ".").strip()
            lon = self.lon_var.get().replace(",", ".").strip()
            alt = self.alt_var.get().replace(",", ".").strip()
            speed = self.speed_var.get().strip()

            if float(lat) < float(lon):
                self._append_log("[WARNING] Lat < Lon. Swapping automatically.\n")
                lat, lon = lon, lat
        except Exception:
            play_sound("error", widget=self)
            messagebox.showerror("Error", "Invalid numeric inputs.")
            return

        self._save_config(
            {
                "proj_dir": proj_dir,
                "lat": lat,
                "lon": lon,
                "speed": speed,
                "vehicle": self.vehicle_var.get(),
                "alt": alt,
            }
        )

        threading.Thread(
            target=self._run_start_sequence,
            args=(proj_dir, lat, lon, alt, speed),
            daemon=True,
        ).start()

    def _run_start_sequence(self, proj_dir, lat, lon, alt, speed):
        self.is_running = True
        self._set_controls(True)
        play_sound("start", widget=self)

        self._append_log("[DOCKER] Starting containers (px4, redis)...\n", "launch")
        self._run_cmd(
            f"{DOCKER_CMD} -f {self.compose_file} up -d",
            cwd=proj_dir,
            log_cmd=False,
        )

        self.status_var.set("Stabilizing...")
        time.sleep(5)

        self.status_var.set("Syncing Redis...")
        if subprocess.run("docker ps | grep redis", shell=True).returncode != 0:
            self._append_log("[ERROR] Redis container not found!\n", "error")
            self.is_running = False
            self._set_controls(False)
            return

        self._append_log("[REDIS] Setting Redis version key...\n", "info")
        self._run_cmd(
            "docker exec redis redis-cli SET root:version:set 3.2.2", log_cmd=False
        )

        for i in range(10, 0, -1):
            self.status_var.set(f"Loading Defaults... {i}s")
            self.progress["value"] = (10 - i) * 10
            time.sleep(1)
        self.progress["value"] = 100

        self.status_var.set("Injecting Coords...")
        self._append_log("[REDIS] Injecting simulation parameters...\n", "info")
        cmds = [
            f'docker exec redis redis-cli SET sim:home_lat "{lat}"',
            f'docker exec redis redis-cli SET sim:home_lon "{lon}"',
            f'docker exec redis redis-cli SET sim:home_alt "{alt}"',
            f'docker exec redis redis-cli SET sim:lat "{lat}"',
            f'docker exec redis redis-cli SET sim:lon "{lon}"',
            f'docker exec redis redis-cli SET sim:alt "{alt}"',
            f'docker exec redis redis-cli SET sim:speed_factor "{speed}"',
            f'docker exec redis redis-cli SET sim:model "{self.vehicle_var.get()}"',
        ]
        for c in cmds:
            self._run_cmd(c, log_cmd=False)

        self.status_var.set("Restarting PX4...")
        self._append_log("[DOCKER] Restarting PX4 container...\n", "launch")
        self._run_cmd(
            f"{DOCKER_CMD} -f {self.compose_file} restart px4",
            cwd=proj_dir,
            log_cmd=False,
        )

        if self.restart_bgc_var.get():
            self._restart_bgc()

        self.status_var.set("Simulation Live")
        self._append_log(f"[SUCCESS] Running at {lat}, {lon}\n", "success")
        play_sound("success", widget=self)

    def _restart_bgc(self):
        self._append_log("[BGC] Restarting Ground Control...\n", "info")

        subprocess.run(["pkill", "-f", "BeagleGroundControl"], stderr=subprocess.DEVNULL)
        time.sleep(1.5)

        if not BGC_DESKTOP_FILE.exists():
            self._append_log("[WARNING] BGC Shortcut not found.\n", "error")
            return

        try:
            cmd = None
            for line in BGC_DESKTOP_FILE.read_text().splitlines():
                if line.strip().startswith("Exec="):
                    cmd = line.split("=", 1)[1].strip()
                    for x in ["%f", "%F", "%u", "%U"]:
                        cmd = cmd.replace(x, "")
                    break
            if cmd:
                subprocess.Popen(
                    cmd.strip(),
                    shell=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._append_log("[BGC] Launched new instance.\n", "launch")
            else:
                self._append_log("[ERROR] No Exec line in desktop file.\n", "error")
        except Exception as e:
            self._append_log(f"[ERROR] BGC launch failed: {e}\n", "error")

    def _stop(self):
        if not messagebox.askyesno("Confirm", "Stop simulation containers?"):
            return
        threading.Thread(target=self._run_stop_sequence, daemon=True).start()

    def _run_stop_sequence(self):
        self.status_var.set("Stopping...")
        proj_dir = self.proj_dir_var.get()

        self._append_log("[DOCKER] Stopping containers...\n", "info")
        self._run_cmd(
            f"{DOCKER_CMD} -f {self.compose_file} down",
            cwd=proj_dir,
            log_cmd=False,
        )

        subprocess.run(["pkill", "-f", "BeagleGroundControl"], stderr=subprocess.DEVNULL)
        self._append_log("[BGC] Ground Control closed.\n", "info")

        self.status_var.set("Stopped")
        self.progress["value"] = 0
        self.is_running = False
        self._set_controls(False)
        self._append_log("[STOP] Containers stopped.\n", "info")
        play_sound("stop", widget=self)

    def _run_cmd(self, cmd, cwd=None, log_cmd=True):
        if log_cmd:
            self._append_log(f"> {cmd}\n")

        try:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if p.stdout.strip():
                for line in p.stdout.strip().splitlines():
                    self._append_log(f"[STDOUT] {line}\n")

            if p.returncode != 0:
                if p.stderr.strip():
                    for line in p.stderr.strip().splitlines():
                        self._append_log(f"[STDERR] {line}\n", "error")
                else:
                    self._append_log(
                        f"[STDERR] Command failed with exit code {p.returncode}.\n",
                        "error",
                    )

        except Exception as e:
            self._append_log(f"[ERROR] Execution exception: {e}\n", "error")

    def _set_controls(self, running: bool):
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if self._log_visible:
                    self._append_log(msg)
        except queue.Empty:
            pass
        self.after(80, self._poll_log_queue)

    def _append_log(self, text: str, tag="normal"):
        if "[LAUNCH]" in text or "Starting" in text:
            tag = "launch"
        elif "[ERROR]" in text or "fail" in text.lower() or "[STDERR]" in text:
            tag = "error"
        elif (
            "[INFO]" in text
            or "[INSTALL]" in text
            or "[REDIS]" in text
            or "[DOCKER]" in text
            or "[TOOL]" in text
        ):
            tag = "info"
        self.log_text.insert(tk.END, text, tag)
        self.log_text.see(tk.END)

    def _open_output_folder(self):
        out = self.out_dir_var.get().strip()
        if out:
            try:
                subprocess.Popen(["xdg-open", out])
            except Exception:
                pass

    def _unique_name(self, base: Path) -> Path:
        if not base.exists():
            return base
        stem, suf = base.stem, base.suffix
        i = 1
        while True:
            cand = base.with_name(f"{stem}-{i}{suf}")
            if not cand.exists():
                return cand
            i += 1

    def _convert_ulg_to_kml(self):
        ulg = self.ulg_path_var.get().strip()
        out_dir = self.out_dir_var.get().strip()
        if not ulg or not Path(ulg).is_file():
            play_sound("error", widget=self, loud=True)
            messagebox.showerror("Missing ULG", "Select a valid .ulg file.")
            return
        if not out_dir or not Path(out_dir).is_dir():
            play_sound("error", widget=self, loud=True)
            messagebox.showerror("Missing output folder", "Select a valid output folder.")
            return

        if not LOCAL_PYULOG_ROOT.exists():
            play_sound("error", widget=self)
            messagebox.showerror("Error", f"Pyulog not found at {LOCAL_PYULOG_ROOT}")
            return

        if str(LOCAL_PYULOG_ROOT) not in sys.path:
            sys.path.insert(0, str(LOCAL_PYULOG_ROOT))

        try:
            import simplekml
            import numpy  # noqa: F401
        except ImportError:
            self._append_log("[TOOL] Dependencies missing. Attempting auto-install...\n", "info")
            if install_deps(["simplekml", "numpy"], log_fn=self._append_log):
                try:
                    import simplekml  # noqa: F401
                    import numpy      # noqa: F401
                except ImportError:
                    play_sound("error", widget=self)
                    messagebox.showerror("Error", "Failed to load dependencies after install.")
                    return
            else:
                play_sound("error", widget=self)
                messagebox.showerror(
                    "Error",
                    "Could not auto-install simplekml/numpy. Please check internet.",
                )
                return

        self.convert_btn.configure(state=tk.DISABLED)
        self.kml_out_last_dir = Path(out_dir)

        def run():
            try:
                self._append_log(
                    f"[TOOL] Importing local pyulog from {LOCAL_PYULOG_ROOT}...\n",
                    "info",
                )
                from pyulog.ulog2kml import convert_ulog2kml

                tgt = self._unique_name(Path(out_dir) / (Path(ulg).stem + ".kml"))

                convert_ulog2kml(ulg, str(tgt))

                self._set_k_status(f"KML created: {tgt.name}", ok=True)
                play_sound("success", widget=self, loud=True)
                self._append_log(f"[SUCCESS] Converted to {tgt.name}\n", "success")
            except Exception as e:
                self._set_k_status(f"Conversion error: {e}", ok=False)
                play_sound("error", widget=self, loud=True)
                self._append_log(f"[ERROR] {e}\n", "error")
            finally:
                try:
                    self.convert_btn.configure(state=tk.NORMAL)
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True).start()

    def _set_k_status(self, text, ok=True):
        try:
            (messagebox.showinfo if ok else messagebox.showerror)("ULG → KML", text)
        except Exception:
            pass

    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                d = json.loads(CONFIG_PATH.read_text())
                self.proj_dir_var.set(d.get("proj_dir", DEFAULT_PROJECT_DIR))
                self.lat_var.set(d.get("lat", ""))
                self.lon_var.set(d.get("lon", ""))
                self.speed_var.set(d.get("speed", "20"))
                self.alt_var.set(d.get("alt", "0"))
                self.ulg_last_dir = Path(d.get("ulg_last_dir", str(Path.home())))
                self.kml_out_last_dir = Path(
                    d.get("kml_out_last_dir", str(Path.home() / "Documents"))
                )
                self.out_dir_var.set(str(self.kml_out_last_dir))
                if d.get("vehicle") in ["octo_beagle", "beagle_m"]:
                    self.vehicle_var.set(d.get("vehicle"))
            except Exception:
                pass

    def _save_config(self, data: dict):
        data["ulg_last_dir"] = str(self.ulg_last_dir)
        data["kml_out_last_dir"] = str(self.kml_out_last_dir)
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _on_close(self):
        if self.is_running and not messagebox.askyesno(
            "Quit?", "Simulation is running. Stop and quit?"
        ):
            return
        if self.is_running:
            self._stop()
        cfg = {
            "proj_dir": self.proj_dir_var.get(),
            "lat": self.lat_var.get(),
            "lon": self.lon_var.get(),
            "speed": self.speed_var.get(),
            "vehicle": self.vehicle_var.get(),
            "alt": self.alt_var.get(),
        }
        self._save_config(cfg)
        self.destroy()


def main():
    app = PX4SimApp()
    app.mainloop()


if __name__ == "__main__":
    main()
