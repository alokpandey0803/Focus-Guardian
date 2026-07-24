"""
Study Blocker — Main UI (CustomTkinter)
Run with:  python main.py
Requires admin/root for website blocking (hosts file writes).
"""
import sys
import os
import platform
import threading
import time
import webbrowser
from datetime import date
import customtkinter as ctk
from tkinter import messagebox

# Local modules
from config_manager import load_config, save_config
from blocker import AppBlocker, send_notification  # website blocking now handled by KeywordBlocker
from timer_widget import StudyTimer
from lock_in import generate_password, verify_password, PASSWORD_LENGTH, random_rethink_quote
from keyword_blocker import KeywordBlocker
from startup_manager import is_startup_enabled, enable_startup, disable_startup
from tray_icon import TrayIcon
from single_instance import SingleInstance
import stats_manager
import app_paths

# ── Appearance ────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT   = "#3B82F6"   # blue
DANGER   = "#EF4444"   # red
SUCCESS  = "#22C55E"   # green
WARNING  = "#F59E0B"   # amber
BG_CARD  = "#1E293B"
BG_MAIN  = "#0F172A"
TEXT     = "#F1F5F9"
MUTED    = "#94A3B8"

FONT_H1   = ("Segoe UI", 28, "bold")
FONT_H2   = ("Segoe UI", 18, "bold")
FONT_H3   = ("Segoe UI", 14, "bold")
FONT_BODY = ("Segoe UI", 13)
FONT_MONO = ("Courier New", 13, "bold")
FONT_PASS = ("Courier New", 11)


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_time(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ── Main Application ──────────────────────────────────────────────────────────

class StudyBlockerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.config_data = load_config()

        # App blocker starts with EMPTY list — only activates when timer/lock-in is on
        self.app_blocker = AppBlocker(notify_callback=self._on_app_killed)
        self.app_blocker.start()

        # Keyword blocker — ALWAYS active regardless of timer or lock-in
        self.keyword_blocker = KeywordBlocker(notify_callback=self._on_keyword_detected)
        self.keyword_blocker.set_keywords(self.config_data.get("blocked_keywords", []))
        self.keyword_blocker.set_adult_content_blocking(self.config_data.get("block_adult_content", False))
        self.keyword_blocker.start()

        self.timer = StudyTimer(
            on_tick=self._on_timer_tick,
            on_finish=self._on_timer_finish,
        )
        self._timer_paused = False
        self._lock_in_password = ""
        self._lock_in_active   = False  # runtime only, not saved

        # Separate countdown timer used only by "Timed" Lock-In mode
        self.lockin_timer = StudyTimer(
            on_tick=self._on_lockin_timer_tick,
            on_finish=self._on_lockin_timer_finish,
        )
        self._lockin_mode = "normal"  # "normal" or "timed"
        self._active_session_start: float | None = None  # for stats tracking
        # Time of the last stats flush to disk. Session time is checkpointed
        # to stats.json periodically (see _periodic_stats_tick) rather than
        # only when blocking ends, so a crash or force-kill doesn't lose an
        # entire session's worth of focused time.
        self._stats_checkpoint: float | None = None

        self._tray = TrayIcon(on_open=self._tray_restore, on_exit=self._tray_exit)

        self._setup_window()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._bring_to_front)

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        self.title("📚 Study Blocker")
        self.geometry("960x660")
        self.minsize(800, 560)
        self.configure(fg_color=BG_MAIN)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Left sidebar
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=BG_CARD)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo area
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=20, pady=(30, 10))
        ctk.CTkLabel(logo_frame, text="📚", font=("Segoe UI", 40)).pack()
        ctk.CTkLabel(logo_frame, text="Study Blocker", font=FONT_H2, text_color=TEXT).pack()
        ctk.CTkLabel(logo_frame, text="Stay focused.", font=FONT_BODY, text_color=MUTED).pack()

        ctk.CTkFrame(sidebar, height=1, fg_color="#334155").pack(fill="x", padx=20, pady=20)

        # Nav buttons
        self._nav_buttons = {}
        nav_items = [
            ("🏠", "Dashboard"),
            ("🌐", "Websites"),
            ("🖥️", "Apps"),
            ("⏱️", "Timer"),
            ("🔑", "Keywords"),
            ("🔒", "Lock-In"),
            ("📊", "Stats"),
            ("⚙️", "Settings"),
        ]
        self._content_frames: dict[str, ctk.CTkFrame] = {}
        self._active_tab = ctk.StringVar(value="Dashboard")

        for icon, label in nav_items:
            btn = ctk.CTkButton(
                sidebar,
                text=f"  {icon}  {label}",
                anchor="w",
                font=FONT_BODY,
                height=44,
                corner_radius=10,
                fg_color="transparent",
                hover_color="#334155",
                text_color=MUTED,
                command=lambda l=label: self._switch_tab(l),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._nav_buttons[label] = btn

        # Status indicator at bottom of sidebar
        ctk.CTkFrame(sidebar, height=1, fg_color="#334155").pack(fill="x", padx=20, pady=20, side="bottom")
        self._status_label = ctk.CTkLabel(
            sidebar, text="● Blocker active", font=("Segoe UI", 12),
            text_color=SUCCESS
        )
        self._status_label.pack(side="bottom", pady=(0, 20))

        # Right content area
        self._content_area = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        self._content_area.pack(side="right", fill="both", expand=True)

        # Build all pages
        self._build_dashboard()
        self._build_websites_page()
        self._build_apps_page()
        self._build_timer_page()
        self._build_keywords_page()
        self._build_lockin_page()
        self._build_stats_page()
        self._build_settings_page()

        self._switch_tab("Dashboard")
        self._periodic_stats_tick()

    def _switch_tab(self, label: str):
        for name, frame in self._content_frames.items():
            frame.pack_forget()
        if label in self._content_frames:
            self._content_frames[label].pack(fill="both", expand=True, padx=30, pady=30)
        if label == "Stats":
            self._refresh_stats_page()
        for name, btn in self._nav_buttons.items():
            if name == label:
                btn.configure(fg_color=ACCENT, text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color=MUTED)
        self._active_tab.set(label)

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _build_dashboard(self):
        f = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent", scrollbar_button_color=BG_CARD)
        self._content_frames["Dashboard"] = f

        ctk.CTkLabel(f, text="Dashboard", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="Your study session at a glance", font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 24))

        # Stats row
        stats = ctk.CTkFrame(f, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 20))

        self._stat_websites = self._stat_card(stats, "🌐", "0", "Blocked Websites")
        self._stat_apps     = self._stat_card(stats, "🖥️", "0", "Blocked Apps")
        self._stat_timer    = self._stat_card(stats, "⏱️", "—", "Timer")
        self._stat_lockin   = self._stat_card(stats, "🔒", "OFF", "Lock-In Mode")

        for card in (self._stat_websites, self._stat_apps, self._stat_timer, self._stat_lockin):
            card.pack(side="left", expand=True, fill="x", padx=6)

        # Quick actions
        ctk.CTkLabel(f, text="Quick Actions", font=FONT_H2, text_color=TEXT).pack(anchor="w", pady=(10, 10))
        qa = ctk.CTkFrame(f, fg_color="transparent")
        qa.pack(fill="x")

        ctk.CTkButton(qa, text="▶  Start 25-min Pomodoro", font=FONT_BODY, height=46,
                      fg_color=SUCCESS, hover_color="#16A34A", corner_radius=10,
                      command=lambda: self._quick_start(25)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(qa, text="▶  Start 50-min Session", font=FONT_BODY, height=46,
                      fg_color=ACCENT, hover_color="#2563EB", corner_radius=10,
                      command=lambda: self._quick_start(50)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(qa, text="🔒  Enable Lock-In", font=FONT_BODY, height=46,
                      fg_color=DANGER, hover_color="#DC2626", corner_radius=10,
                      command=lambda: self._switch_tab("Lock-In")).pack(side="left")

        # Recent activity log
        ctk.CTkLabel(f, text="Activity Log", font=FONT_H2, text_color=TEXT).pack(anchor="w", pady=(30, 10))
        self._log_box = ctk.CTkTextbox(f, height=200, font=FONT_BODY, fg_color=BG_CARD,
                                       text_color=MUTED, corner_radius=12, wrap="word")
        self._log_box.pack(fill="x")
        self._log_box.configure(state="disabled")
        self._log("Study Blocker started. Good luck! 💪")

        self._update_stat_cards()

    def _stat_card(self, parent, icon, value, label):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=18, pady=16)
        ctk.CTkLabel(inner, text=icon, font=("Segoe UI", 26)).pack()
        lbl_val = ctk.CTkLabel(inner, text=value, font=FONT_H2, text_color=TEXT)
        lbl_val.pack()
        ctk.CTkLabel(inner, text=label, font=("Segoe UI", 11), text_color=MUTED).pack()
        card._value_label = lbl_val
        return card

    def _update_stat_cards(self):
        self._stat_websites._value_label.configure(text=str(len(self.config_data["blocked_websites"])))
        self._stat_apps._value_label.configure(text=str(len(self.config_data["blocked_apps"])))
        timer_text = fmt_time(self.timer.remaining) if self.timer.remaining > 0 else "—"
        self._stat_timer._value_label.configure(text=timer_text)
        self._stat_lockin._value_label.configure(
            text="ON" if self._lock_in_active else "OFF",
            text_color=DANGER if self._lock_in_active else TEXT,
        )

    def _quick_start(self, minutes: int):
        self._start_timer(minutes)
        self._switch_tab("Timer")

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── Websites ──────────────────────────────────────────────────────────────

    def _build_websites_page(self):
        f = ctk.CTkFrame(self._content_area, fg_color="transparent")
        self._content_frames["Websites"] = f

        ctk.CTkLabel(f, text="Blocked Websites", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="Blocked sites are monitored by title — the tab is closed the moment you open one. No admin rights needed.", font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 20))

        # Input row
        input_row = ctk.CTkFrame(f, fg_color="transparent")
        input_row.pack(fill="x", pady=(0, 16))
        self._site_entry = ctk.CTkEntry(input_row, placeholder_text="e.g. youtube.com", height=42,
                                         font=FONT_BODY, fg_color=BG_CARD, corner_radius=10, border_width=0)
        self._site_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._site_entry.bind("<Return>", lambda e: self._add_site())
        ctk.CTkButton(input_row, text="+ Add", height=42, width=100, corner_radius=10,
                       fg_color=ACCENT, hover_color="#2563EB", font=FONT_BODY,
                       command=self._add_site).pack(side="left")

        # List
        self._site_list_frame = ctk.CTkScrollableFrame(f, fg_color=BG_CARD, corner_radius=12,
                                                        scrollbar_button_color=BG_MAIN)
        self._site_list_frame.pack(fill="both", expand=True)

        # Apply button
        ctk.CTkButton(f, text="🔍  Update Active Block List", height=46, corner_radius=10,
                       fg_color=ACCENT, hover_color="#2563EB", font=FONT_BODY,
                       command=self._apply_website_blocks).pack(fill="x", pady=(16, 0))

        self._refresh_site_list()

    def _add_site(self):
        # Adding is allowed even during Lock-In — only removing is frozen,
        # since adding more restrictions can't be used to weasel out of one.
        site = self._site_entry.get().strip().lower()
        if not site:
            return
        site = site.removeprefix("http://").removeprefix("https://").split("/")[0]
        if site and site not in self.config_data["blocked_websites"]:
            self.config_data["blocked_websites"].append(site)
            save_config(self.config_data)
            self._site_entry.delete(0, "end")
            self._refresh_site_list()
            self._update_stat_cards()
            self._log(f"Added website to block list: {site} (will block when timer/lock-in is active)")
            if self._is_blocking_active():
                self._apply_website_blocks(silent=True)

    def _remove_site(self, site: str):
        if self._block_if_locked_in("remove sites from your blocked-websites list"):
            return
        if site in self.config_data["blocked_websites"]:
            self.config_data["blocked_websites"].remove(site)
            save_config(self.config_data)
            self._refresh_site_list()
            self._update_stat_cards()
            self._log(f"Removed website: {site} — unblocked immediately")
            # Always re-apply (removes it from hosts file even if blocking active)
            self._apply_website_blocks(silent=True)

    def _refresh_site_list(self):
        for w in self._site_list_frame.winfo_children():
            w.destroy()
        sites = self.config_data["blocked_websites"]
        if not sites:
            ctk.CTkLabel(self._site_list_frame, text="No websites blocked yet.",
                         font=FONT_BODY, text_color=MUTED).pack(pady=30)
            return
        for site in sites:
            row = ctk.CTkFrame(self._site_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=f"🌐  {site}", font=FONT_BODY, text_color=TEXT).pack(side="left")
            ctk.CTkButton(row, text="Remove", width=80, height=30, corner_radius=8,
                           fg_color=DANGER, hover_color="#DC2626", font=("Segoe UI", 12),
                           command=lambda s=site: self._remove_site(s)).pack(side="right")

    def _apply_website_blocks(self, silent=False):
        """Update the keyword_blocker's live site list if blocking is currently active."""
        sites = self.config_data.get("blocked_websites", [])
        if self._is_blocking_active():
            self.keyword_blocker.set_active_blocked_sites(sites)
            self._log(f"🔒 Site block list updated ({len(sites)} sites active).")
            if not silent:
                messagebox.showinfo("Updated", f"{len(sites)} website(s) are now being monitored.\nAny tab matching a blocked site will be closed immediately.")
        else:
            self._log(f"📋 Site list saved ({len(sites)} sites — will activate when timer starts).")

    def _apply_blocks_silent(self):
        self._apply_website_blocks(silent=True)

    # ── Apps ──────────────────────────────────────────────────────────────────

    def _build_apps_page(self):
        f = ctk.CTkFrame(self._content_area, fg_color="transparent")
        self._content_frames["Apps"] = f

        ctk.CTkLabel(f, text="Blocked Apps", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="Matching processes are killed the moment they start", font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 20))

        input_row = ctk.CTkFrame(f, fg_color="transparent")
        input_row.pack(fill="x", pady=(0, 16))
        self._app_entry = ctk.CTkEntry(input_row, placeholder_text="e.g. discord, spotify, steam",
                                        height=42, font=FONT_BODY, fg_color=BG_CARD,
                                        corner_radius=10, border_width=0)
        self._app_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._app_entry.bind("<Return>", lambda e: self._add_app())
        ctk.CTkButton(input_row, text="+ Add", height=42, width=100, corner_radius=10,
                       fg_color=ACCENT, hover_color="#2563EB", font=FONT_BODY,
                       command=self._add_app).pack(side="left")

        ctk.CTkLabel(f, text="Enter part of the process name (e.g. 'discord' matches 'Discord.exe')",
                     font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(0, 10))

        self._app_list_frame = ctk.CTkScrollableFrame(f, fg_color=BG_CARD, corner_radius=12,
                                                       scrollbar_button_color=BG_MAIN)
        self._app_list_frame.pack(fill="both", expand=True)

        self._refresh_app_list()

    def _add_app(self):
        # Adding is allowed even during Lock-In — only removing is frozen.
        app = self._app_entry.get().strip().lower()
        if not app:
            return
        if app not in self.config_data["blocked_apps"]:
            self.config_data["blocked_apps"].append(app)
            save_config(self.config_data)
            if self._is_blocking_active():
                self.app_blocker.set_blocked_apps(self.config_data["blocked_apps"])
            self._app_entry.delete(0, "end")
            self._refresh_app_list()
            self._update_stat_cards()
            self._log(f"Added app to block list: {app} (will block when timer/lock-in is active)")

    def _remove_app(self, app: str):
        if self._block_if_locked_in("remove apps from your blocked-apps list"):
            return
        if app in self.config_data["blocked_apps"]:
            self.config_data["blocked_apps"].remove(app)
            save_config(self.config_data)
            if self._is_blocking_active():
                self.app_blocker.set_blocked_apps(self.config_data["blocked_apps"])
            self._refresh_app_list()
            self._update_stat_cards()
            self._log(f"Removed app from block list: {app}")

    def _refresh_app_list(self):
        for w in self._app_list_frame.winfo_children():
            w.destroy()
        apps = self.config_data["blocked_apps"]
        if not apps:
            ctk.CTkLabel(self._app_list_frame, text="No apps blocked yet.",
                         font=FONT_BODY, text_color=MUTED).pack(pady=30)
            return
        for app in apps:
            row = ctk.CTkFrame(self._app_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=f"🖥️  {app}", font=FONT_BODY, text_color=TEXT).pack(side="left")
            ctk.CTkButton(row, text="Remove", width=80, height=30, corner_radius=8,
                           fg_color=DANGER, hover_color="#DC2626", font=("Segoe UI", 12),
                           command=lambda a=app: self._remove_app(a)).pack(side="right")

    def _on_app_killed(self, app_name: str):
        """Called from background thread — schedule on main thread."""
        self.after(0, lambda: self._log(f"🚫 Blocked & killed: {app_name}"))

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _build_timer_page(self):
        f = ctk.CTkFrame(self._content_area, fg_color="transparent")
        self._content_frames["Timer"] = f

        ctk.CTkLabel(f, text="Study Timer", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="Set your focus duration and track your session", font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 20))

        # Big clock display
        clock_frame = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=20)
        clock_frame.pack(pady=(0, 24))
        self._clock_label = ctk.CTkLabel(clock_frame, text="00:00", font=("Segoe UI", 72, "bold"),
                                          text_color=ACCENT)
        self._clock_label.pack(padx=60, pady=24)
        self._timer_status_label = ctk.CTkLabel(clock_frame, text="Not started",
                                                  font=FONT_BODY, text_color=MUTED)
        self._timer_status_label.pack(pady=(0, 16))

        # ── Custom time input ──────────────────────────────────────────────
        custom_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        custom_card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(custom_card, text="Custom Duration", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=18, pady=(14, 8))

        time_input_row = ctk.CTkFrame(custom_card, fg_color="transparent")
        time_input_row.pack(padx=18, pady=(0, 14))

        # Hours
        ctk.CTkLabel(time_input_row, text="Hours", font=("Segoe UI", 11), text_color=MUTED).grid(row=0, column=0, padx=(0, 4))
        self._hours_var = ctk.StringVar(value="0")
        ctk.CTkEntry(time_input_row, textvariable=self._hours_var, width=70, height=42,
                     font=FONT_H3, fg_color="#0F172A", corner_radius=10, border_width=0,
                     justify="center").grid(row=1, column=0, padx=(0, 6))

        ctk.CTkLabel(time_input_row, text=":", font=("Segoe UI", 28, "bold"),
                     text_color=MUTED).grid(row=1, column=1, padx=4)

        # Minutes
        ctk.CTkLabel(time_input_row, text="Minutes", font=("Segoe UI", 11), text_color=MUTED).grid(row=0, column=2, padx=(4, 0))
        saved_mins = self.config_data.get("timer_minutes", 25)
        self._minutes_var = ctk.StringVar(value=str(saved_mins % 60 if saved_mins < 60 else saved_mins))
        ctk.CTkEntry(time_input_row, textvariable=self._minutes_var, width=70, height=42,
                     font=FONT_H3, fg_color="#0F172A", corner_radius=10, border_width=0,
                     justify="center").grid(row=1, column=2, padx=(6, 20))

        # Presets inside the card
        ctk.CTkLabel(time_input_row, text="Presets:", font=FONT_BODY, text_color=MUTED).grid(row=1, column=3, padx=(0, 8))
        presets_frame = ctk.CTkFrame(time_input_row, fg_color="transparent")
        presets_frame.grid(row=1, column=4)
        for total_mins, label in [(5, "5 min"), (25, "Pomodoro"), (50, "Deep Work"), (90, "Flow"), (120, "2 hrs")]:
            ctk.CTkButton(presets_frame, text=label, width=82, height=38, corner_radius=8,
                           fg_color="#334155", hover_color=ACCENT, font=("Segoe UI", 12),
                           command=lambda m=total_mins: self._set_preset(m)).pack(side="left", padx=3)

        # Controls
        ctrl = ctk.CTkFrame(f, fg_color="transparent")
        ctrl.pack(pady=(0, 16))
        self._btn_start = ctk.CTkButton(ctrl, text="▶  Start", width=130, height=48, corner_radius=12,
                                         fg_color=SUCCESS, hover_color="#16A34A", font=FONT_H3,
                                         command=self._timer_start_pause)
        self._btn_start.pack(side="left", padx=8)
        ctk.CTkButton(ctrl, text="⏹  Stop", width=130, height=48, corner_radius=12,
                       fg_color=DANGER, hover_color="#DC2626", font=FONT_H3,
                       command=self._timer_stop).pack(side="left", padx=8)
        ctk.CTkButton(ctrl, text="+ 5 min", width=100, height=48, corner_radius=12,
                       fg_color="#334155", hover_color="#475569", font=FONT_H3,
                       command=lambda: self._add_time(5)).pack(side="left", padx=8)
        ctk.CTkButton(ctrl, text="+ 10 min", width=110, height=48, corner_radius=12,
                       fg_color="#334155", hover_color="#475569", font=FONT_H3,
                       command=lambda: self._add_time(10)).pack(side="left", padx=8)
        ctk.CTkButton(ctrl, text="+ 30 min", width=110, height=48, corner_radius=12,
                       fg_color="#334155", hover_color="#475569", font=FONT_H3,
                       command=lambda: self._add_time(30)).pack(side="left", padx=8)

        # Progress bar
        self._timer_progress = ctk.CTkProgressBar(f, height=14, corner_radius=7,
                                                    fg_color="#334155", progress_color=ACCENT)
        self._timer_progress.pack(fill="x", pady=(0, 8))
        self._timer_progress.set(0)

    def _set_preset(self, total_minutes: int):
        h, m = divmod(total_minutes, 60)
        self._hours_var.set(str(h))
        self._minutes_var.set(str(m))

    def _timer_start_pause(self):
        if self.timer.is_running:
            self.timer.pause()
            self._timer_paused = True
            self._btn_start.configure(text="▶  Resume", fg_color=ACCENT)
            self._timer_status_label.configure(text="Paused", text_color=WARNING)
        elif self._timer_paused and self.timer.remaining > 0:
            self.timer.resume()
            self._timer_paused = False
            self._btn_start.configure(text="⏸  Pause", fg_color=WARNING)
            self._timer_status_label.configure(text="Focusing…", text_color=SUCCESS)
        else:
            self._start_timer()

    def _start_timer(self, minutes: int = None):
        if self.timer.is_running:
            # Already running — starting again would restart it from
            # scratch, which is almost never what someone wants when they
            # click a preset or "Start" mid-session. Let pause/resume or
            # the Timer page's Stop button do that explicitly instead.
            messagebox.showinfo(
                "Timer Already Running",
                f"A timer is already running ({fmt_time(self.timer.remaining)} left).\n"
                "Pause or stop it first if you want to start a different one.",
            )
            self._switch_tab("Timer")
            return
        if minutes is None:
            try:
                h = int(self._hours_var.get() or 0)
                m = int(self._minutes_var.get() or 0)
                minutes = h * 60 + m
            except ValueError:
                minutes = 25
        minutes = max(1, min(minutes, 1440))  # max 24 hrs
        h, m = divmod(minutes, 60)
        self._hours_var.set(str(h))
        self._minutes_var.set(str(m))
        self.config_data["timer_minutes"] = minutes
        save_config(self.config_data)

        self._timer_total = minutes * 60
        self.timer.start(minutes)
        self._timer_paused = False
        self._btn_start.configure(text="⏸  Pause", fg_color=WARNING)
        self._timer_status_label.configure(text="Focusing…", text_color=SUCCESS)
        self._log(f"⏱️ Timer started: {fmt_time(minutes * 60)}")
        # Activate website + app blocking now that timer is running
        self._apply_active_blocks()
        self._update_status_label()

    def _timer_stop(self):
        self.timer.stop()
        self._timer_paused = False
        self._btn_start.configure(text="▶  Start", fg_color=SUCCESS)
        self._clock_label.configure(text="00:00", text_color=ACCENT)
        self._timer_status_label.configure(text="Not started", text_color=MUTED)
        self._timer_progress.set(0)
        self._update_stat_cards()
        # Remove blocks only if lock-in is also not active
        if not self._lock_in_active:
            self._remove_active_blocks()
        self._update_status_label()

    def _add_time(self, mins: int):
        self.timer.add_minutes(mins)
        self._log(f"Added {mins} minutes to timer")

    def _on_timer_tick(self, remaining: int):
        self.after(0, lambda: self._update_timer_display(remaining))

    def _update_timer_display(self, remaining: int):
        self._clock_label.configure(text=fmt_time(remaining))
        total = getattr(self, "_timer_total", 1) or 1
        progress = 1.0 - (remaining / total)
        self._timer_progress.set(min(1.0, max(0.0, progress)))
        self._update_stat_cards()

    def _on_timer_finish(self):
        self.after(0, self._timer_finished)

    def _timer_finished(self):
        self._timer_stop()
        send_notification("⏱️ Study Blocker", "Time's up! Great work. Take a break.")
        self._log("✅ Timer finished! Great session.")
        messagebox.showinfo("Time's Up!", "Your study session is complete!\nTake a well-deserved break. 🎉")

    # ── Lock-In Mode ──────────────────────────────────────────────────────────

    def _build_lockin_page(self):
        f = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent",
                                    scrollbar_button_color=BG_CARD)
        self._content_frames["Lock-In"] = f

        ctk.CTkLabel(f, text="Lock-In Mode", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text=f"Forces extreme focus — type an {PASSWORD_LENGTH}-character password to escape",
                     font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 16))

        # ── Mode selection card ─────────────────────────────────────────────
        mode_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=16)
        mode_card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(mode_card, text="Lock-In Type", font=FONT_H3, text_color=TEXT).pack(
            anchor="w", padx=18, pady=(14, 8))

        self._lockin_mode_var = ctk.StringVar(value="normal")
        self._radio_normal = ctk.CTkRadioButton(
            mode_card, text="🔒  Normal — stays locked until you type the password",
            variable=self._lockin_mode_var, value="normal", font=FONT_BODY,
            command=self._on_lockin_mode_change)
        self._radio_normal.pack(anchor="w", padx=18, pady=4)

        self._radio_timed = ctk.CTkRadioButton(
            mode_card, text="⏱️  Timed — auto-unlocks after a set time (password still works for an early exit)",
            variable=self._lockin_mode_var, value="timed", font=FONT_BODY,
            command=self._on_lockin_mode_change)
        self._radio_timed.pack(anchor="w", padx=18, pady=(4, 8))

        # Duration inputs — only shown/used when "Timed" is selected
        self._lockin_time_frame = ctk.CTkFrame(mode_card, fg_color="transparent")

        time_input_row = ctk.CTkFrame(self._lockin_time_frame, fg_color="transparent")
        time_input_row.pack(padx=18, pady=(0, 14))

        ctk.CTkLabel(time_input_row, text="Hours", font=("Segoe UI", 11), text_color=MUTED).grid(
            row=0, column=0, padx=(0, 4))
        self._lockin_hours_var = ctk.StringVar(value="0")
        ctk.CTkEntry(time_input_row, textvariable=self._lockin_hours_var, width=70, height=42,
                     font=FONT_H3, fg_color="#0F172A", corner_radius=10, border_width=0,
                     justify="center").grid(row=1, column=0, padx=(0, 6))

        ctk.CTkLabel(time_input_row, text=":", font=("Segoe UI", 28, "bold"),
                     text_color=MUTED).grid(row=1, column=1, padx=4)

        ctk.CTkLabel(time_input_row, text="Minutes", font=("Segoe UI", 11), text_color=MUTED).grid(
            row=0, column=2, padx=(4, 0))
        self._lockin_minutes_var = ctk.StringVar(value="25")
        ctk.CTkEntry(time_input_row, textvariable=self._lockin_minutes_var, width=70, height=42,
                     font=FONT_H3, fg_color="#0F172A", corner_radius=10, border_width=0,
                     justify="center").grid(row=1, column=2, padx=(6, 20))

        ctk.CTkLabel(time_input_row, text="Presets:", font=FONT_BODY, text_color=MUTED).grid(
            row=1, column=3, padx=(0, 8))
        lockin_presets_frame = ctk.CTkFrame(time_input_row, fg_color="transparent")
        lockin_presets_frame.grid(row=1, column=4)
        for total_mins, label in [(25, "Pomodoro"), (50, "Deep Work"), (90, "Flow"), (120, "2 hrs")]:
            ctk.CTkButton(lockin_presets_frame, text=label, width=82, height=38, corner_radius=8,
                           fg_color="#334155", hover_color=ACCENT, font=("Segoe UI", 12),
                           command=lambda m=total_mins: self._set_lockin_preset(m)).pack(side="left", padx=3)

        # Countdown display shown once a timed lock-in is active
        self._lockin_countdown_label = ctk.CTkLabel(
            mode_card, text="", font=("Segoe UI", 13, "bold"), text_color=ACCENT)

        self._on_lockin_mode_change()

        # ── Status card ───────────────────────────────────────────────────
        self._lockin_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=16)
        self._lockin_card.pack(fill="x", pady=(0, 16))

        top_row = ctk.CTkFrame(self._lockin_card, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=18)

        left_status = ctk.CTkFrame(top_row, fg_color="transparent")
        left_status.pack(side="left", expand=True)
        self._lockin_icon_label  = ctk.CTkLabel(left_status, text="🔓", font=("Segoe UI", 44))
        self._lockin_icon_label.pack()
        self._lockin_status_text = ctk.CTkLabel(left_status, text="INACTIVE",
                                                  font=("Segoe UI", 20, "bold"), text_color=MUTED)
        self._lockin_status_text.pack(pady=4)
        self._lockin_desc = ctk.CTkLabel(left_status, text="Click Enable to enter full lock-in mode",
                                          font=FONT_BODY, text_color=MUTED)
        self._lockin_desc.pack()

        right_btn = ctk.CTkFrame(top_row, fg_color="transparent")
        right_btn.pack(side="right")
        self._btn_enable_lockin = ctk.CTkButton(right_btn, text="🔒  Enable Lock-In",
                                                  width=180, height=50, corner_radius=12,
                                                  font=FONT_H3, fg_color=DANGER,
                                                  hover_color="#DC2626",
                                                  command=self._enable_lockin)
        self._btn_enable_lockin.pack()
        ctk.CTkLabel(right_btn,
                     text="Cannot close app or remove\nblocks while active.",
                     font=("Segoe UI", 11), text_color=MUTED).pack(pady=(8, 0))

        # ── Password unlock section (hidden until active) ─────────────────
        self._password_frame = ctk.CTkFrame(f, fg_color="#1a0a0a", corner_radius=16,
                                             border_width=2, border_color=DANGER)

        ctk.CTkLabel(self._password_frame,
                     text="🔑  TYPE THIS EXACT PASSWORD TO EXIT LOCK-IN",
                     font=("Segoe UI", 13, "bold"), text_color=DANGER).pack(pady=(18, 6))
        ctk.CTkLabel(self._password_frame,
                     text=f"{PASSWORD_LENGTH} characters · case-sensitive · every character must match",
                     font=("Segoe UI", 11), text_color=MUTED).pack()

        # Password display — plain label, deliberately NOT selectable/copyable.
        # (If it were copy-pasteable, typing it out would be pointless —
        # the whole point is that the person has to actually read and type
        # it themselves, character by character.)
        self._password_box = ctk.CTkLabel(self._password_frame, text="",
                                           font=("Courier New", 18, "bold"),
                                           fg_color="#0d0d0d", text_color="#FCD34D",
                                           corner_radius=10, height=70)
        self._password_box.pack(fill="x", padx=20, pady=(12, 4))
        # Block text selection / copy shortcuts on the label itself.
        for seq in ("<Button-1>", "<B1-Motion>", "<Control-c>", "<Control-C>"):
            self._password_box.bind(seq, lambda e: "break")

        ctk.CTkLabel(self._password_frame,
                     text="🚫 Copy/paste is disabled on purpose — read it and type it out.",
                     font=("Segoe UI", 11), text_color=MUTED).pack()

        ctk.CTkFrame(self._password_frame, height=1, fg_color="#3f1010").pack(fill="x", padx=20, pady=16)

        # Input entry
        ctk.CTkLabel(self._password_frame, text="Type the password here to unlock:",
                     font=FONT_BODY, text_color=TEXT).pack(anchor="w", padx=20)

        self._unlock_entry = ctk.CTkEntry(self._password_frame,
                                           placeholder_text=f"Type all {PASSWORD_LENGTH} characters exactly…",
                                           height=46, font=("Courier New", 13),
                                           fg_color="#0F172A", corner_radius=10, border_width=0)
        self._unlock_entry.pack(fill="x", padx=20, pady=(6, 4))
        self._unlock_entry.bind("<KeyRelease>", self._on_unlock_key)
        # Block paste — the password must be typed manually, not pasted in
        # (even though it's no longer shown anywhere it could be copied from).
        for seq in ("<Control-v>", "<Control-V>", "<Button-2>", "<<Paste>>"):
            self._unlock_entry.bind(seq, lambda e: "break")

        # Live match counter
        self._match_label = ctk.CTkLabel(self._password_frame, text=f"0 / {PASSWORD_LENGTH} characters typed",
                                          font=("Segoe UI", 12), text_color=MUTED)
        self._match_label.pack(anchor="w", padx=20)

        self._match_bar = ctk.CTkProgressBar(self._password_frame, height=8, corner_radius=4,
                                              fg_color="#334155", progress_color=ACCENT)
        self._match_bar.pack(fill="x", padx=20, pady=(4, 8))
        self._match_bar.set(0)

        ctk.CTkButton(self._password_frame, text="🔓  Unlock", height=46, corner_radius=10,
                       fg_color=DANGER, hover_color="#991b1b", font=FONT_H3,
                       command=self._try_unlock).pack(fill="x", padx=20, pady=(0, 20))

        # ── Two columns: Website Blocker | App Blocker ────────────────────
        ctk.CTkLabel(f, text="Blockers", font=FONT_H2, text_color=TEXT).pack(anchor="w", pady=(16, 8))
        ctk.CTkLabel(f, text="Add websites and apps to block from here — you can add during lock-in but not remove",
                     font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(0, 12))

        cols = ctk.CTkFrame(f, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        # ── Website blocker column ────────────────────────────────────────
        web_card = ctk.CTkFrame(cols, fg_color=BG_CARD, corner_radius=14)
        web_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ctk.CTkLabel(web_card, text="🌐  Website Blocker", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=14, pady=(14, 8))

        web_input = ctk.CTkFrame(web_card, fg_color="transparent")
        web_input.pack(fill="x", padx=14, pady=(0, 8))
        self._lockin_site_entry = ctk.CTkEntry(web_input, placeholder_text="youtube.com",
                                                height=38, font=FONT_BODY, fg_color="#0F172A",
                                                corner_radius=8, border_width=0)
        self._lockin_site_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._lockin_site_entry.bind("<Return>", lambda e: self._lockin_add_site())
        ctk.CTkButton(web_input, text="+ Add", width=80, height=38, corner_radius=8,
                       fg_color=ACCENT, hover_color="#2563EB", font=("Segoe UI", 12),
                       command=self._lockin_add_site).pack(side="left")

        self._lockin_site_list = ctk.CTkScrollableFrame(web_card, height=200,
                                                         fg_color="#0F172A", corner_radius=10,
                                                         scrollbar_button_color=BG_CARD)
        self._lockin_site_list.pack(fill="x", padx=14, pady=(0, 14))

        # ── App blocker column ────────────────────────────────────────────
        app_card = ctk.CTkFrame(cols, fg_color=BG_CARD, corner_radius=14)
        app_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(app_card, text="🖥️  App Blocker", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=14, pady=(14, 8))

        app_input = ctk.CTkFrame(app_card, fg_color="transparent")
        app_input.pack(fill="x", padx=14, pady=(0, 8))
        self._lockin_app_entry = ctk.CTkEntry(app_input, placeholder_text="discord, spotify…",
                                               height=38, font=FONT_BODY, fg_color="#0F172A",
                                               corner_radius=8, border_width=0)
        self._lockin_app_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._lockin_app_entry.bind("<Return>", lambda e: self._lockin_add_app())
        ctk.CTkButton(app_input, text="+ Add", width=80, height=38, corner_radius=8,
                       fg_color=ACCENT, hover_color="#2563EB", font=("Segoe UI", 12),
                       command=self._lockin_add_app).pack(side="left")

        self._lockin_app_list = ctk.CTkScrollableFrame(app_card, height=200,
                                                        fg_color="#0F172A", corner_radius=10,
                                                        scrollbar_button_color=BG_CARD)
        self._lockin_app_list.pack(fill="x", padx=14, pady=(0, 14))

        self._refresh_lockin_lists()

    # ── Lock-In list helpers ──────────────────────────────────────────────────

    def _lockin_add_site(self):
        # Adding is allowed even during Lock-In — only removing is frozen.
        site = self._lockin_site_entry.get().strip().lower()
        if not site:
            return
        site = site.removeprefix("http://").removeprefix("https://").split("/")[0]
        if site and site not in self.config_data["blocked_websites"]:
            self.config_data["blocked_websites"].append(site)
            save_config(self.config_data)
            self._lockin_site_entry.delete(0, "end")
            self._refresh_lockin_lists()
            self._refresh_site_list()
            self._update_stat_cards()
            self._apply_website_blocks(silent=True)
            self._log(f"Added website (lock-in): {site}")

    def _lockin_add_app(self):
        # Adding is allowed even during Lock-In — only removing is frozen.
        app = self._lockin_app_entry.get().strip().lower()
        if not app:
            return
        if app not in self.config_data["blocked_apps"]:
            self.config_data["blocked_apps"].append(app)
            save_config(self.config_data)
            if self._is_blocking_active():
                self.app_blocker.set_blocked_apps(self.config_data["blocked_apps"])
            self._lockin_app_entry.delete(0, "end")
            self._refresh_lockin_lists()
            self._refresh_app_list()
            self._update_stat_cards()
            self._log(f"Added app (lock-in): {app}")

    def _refresh_lockin_lists(self):
        # Websites
        for w in self._lockin_site_list.winfo_children():
            w.destroy()
        sites = self.config_data["blocked_websites"]
        if not sites:
            ctk.CTkLabel(self._lockin_site_list, text="None blocked yet",
                         font=("Segoe UI", 12), text_color=MUTED).pack(pady=16)
        else:
            for site in sites:
                row = ctk.CTkFrame(self._lockin_site_list, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=f"🌐 {site}", font=("Segoe UI", 12),
                             text_color=TEXT).pack(side="left")
                if not self._lock_in_active:
                    ctk.CTkButton(row, text="✕", width=28, height=24, corner_radius=6,
                                   fg_color=DANGER, hover_color="#DC2626", font=("Segoe UI", 11),
                                   command=lambda s=site: self._remove_site(s) or self._refresh_lockin_lists()
                                   ).pack(side="right")

        # Apps
        for w in self._lockin_app_list.winfo_children():
            w.destroy()
        apps = self.config_data["blocked_apps"]
        if not apps:
            ctk.CTkLabel(self._lockin_app_list, text="None blocked yet",
                         font=("Segoe UI", 12), text_color=MUTED).pack(pady=16)
        else:
            for app in apps:
                row = ctk.CTkFrame(self._lockin_app_list, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=f"🖥️ {app}", font=("Segoe UI", 12),
                             text_color=TEXT).pack(side="left")
                if not self._lock_in_active:
                    ctk.CTkButton(row, text="✕", width=28, height=24, corner_radius=6,
                                   fg_color=DANGER, hover_color="#DC2626", font=("Segoe UI", 11),
                                   command=lambda a=app: self._remove_app(a) or self._refresh_lockin_lists()
                                   ).pack(side="right")

    # ── Lock-In enable / unlock ───────────────────────────────────────────────

    def _set_lockin_preset(self, total_minutes: int):
        h, m = divmod(total_minutes, 60)
        self._lockin_hours_var.set(str(h))
        self._lockin_minutes_var.set(str(m))

    def _on_lockin_mode_change(self):
        """Show/hide the duration picker depending on Normal vs Timed selection."""
        if self._lockin_mode_var.get() == "timed":
            self._lockin_time_frame.pack(fill="x", padx=0, pady=(0, 4))
        else:
            self._lockin_time_frame.pack_forget()

    def _enable_lockin(self):
        mode = self._lockin_mode_var.get()

        if mode == "timed":
            try:
                h = int(self._lockin_hours_var.get() or 0)
                m = int(self._lockin_minutes_var.get() or 0)
                minutes = h * 60 + m
            except ValueError:
                minutes = 25
            minutes = max(1, min(minutes, 1440))  # 1 min .. 24 hrs
            h, m = divmod(minutes, 60)
            self._lockin_hours_var.set(str(h))
            self._lockin_minutes_var.set(str(m))

            confirm = messagebox.askyesno(
                "Enable Timed Lock-In Mode?",
                f"Lock-In will run for {fmt_time(minutes * 60)} and auto-unlock when it ends.\n\n"
                "While it's running you will NOT be able to:\n"
                "• Fully exit the app (you can still minimize it to the tray)\n"
                "• Add or remove anything from your website/app/keyword block lists\n\n"
                f"You can still exit early by typing the {PASSWORD_LENGTH}-character password.\n"
                "Screenshot or write down the password before locking in!\n\n"
                "Are you sure?",
            )
        else:
            minutes = None
            confirm = messagebox.askyesno(
                "Enable Lock-In Mode?",
                "You will NOT be able to:\n"
                "• Fully exit the app (you can still minimize it to the tray)\n"
                "• Add or remove anything from your website/app/keyword block lists\n"
                f"• Exit without typing the {PASSWORD_LENGTH}-character password\n\n"
                "Screenshot or write down the password before locking in!\n\n"
                "Are you sure?",
            )

        if not confirm:
            return

        self._lockin_mode = mode
        self._lock_in_password = generate_password()
        self._lock_in_active = True

        if mode == "timed":
            self._lockin_total_seconds = minutes * 60
            self.lockin_timer.start(minutes)
            self._log(f"🔒 Timed Lock-In ACTIVATED for {fmt_time(minutes * 60)}.")
        else:
            self._log("🔒 Lock-In Mode ACTIVATED.")

        self._update_lockin_ui()
        self._refresh_lockin_lists()
        self._update_stat_cards()
        self._apply_active_blocks()
        self._update_status_label()
        send_notification("🔒 Study Blocker", "Lock-In Mode enabled. No distractions allowed!")

    def _on_unlock_key(self, event=None):
        entered = self._unlock_entry.get()
        n = len(entered)
        total = len(self._lock_in_password) or PASSWORD_LENGTH
        # Count matching chars from start
        correct = sum(1 for a, b in zip(entered, self._lock_in_password) if a == b)
        self._match_label.configure(
            text=f"{n} / {total} characters typed  ·  {correct} correct from start",
            text_color=SUCCESS if n == total and correct == total else (WARNING if correct > 0 else MUTED),
        )
        self._match_bar.set(min(1.0, n / total))

    def _on_lockin_timer_tick(self, remaining: int):
        self.after(0, lambda: self._update_lockin_countdown(remaining))

    def _update_lockin_countdown(self, remaining: int):
        if self._lock_in_active and self._lockin_mode == "timed":
            self._lockin_countdown_label.configure(text=f"⏱️ Auto-unlocks in {fmt_time(remaining)}")

    def _on_lockin_timer_finish(self):
        self.after(0, self._lockin_timed_finished)

    def _lockin_timed_finished(self):
        if not self._lock_in_active:
            return
        self._lock_in_active = False
        self._lock_in_password = ""
        self._log("⏱️ Timed Lock-In finished — auto-unlocked.")
        self._update_lockin_ui()
        self._refresh_lockin_lists()
        self._update_stat_cards()
        self._update_status_label()
        # Remove blocks if the study timer is also not running
        if not self.timer.is_running:
            self._remove_active_blocks()
        send_notification("🔓 Study Blocker", "Lock-In time is up — unlocked automatically!")
        messagebox.showinfo("Time's Up!", "Your Lock-In session is complete. Welcome back! 🎉")

    def _update_lockin_ui(self):
        if self._lock_in_active:
            self._lockin_icon_label.configure(text="🔒")
            self._lockin_status_text.configure(text="ACTIVE", text_color=DANGER)
            if self._lockin_mode == "timed":
                self._lockin_desc.configure(text="Timed Lock-In running. Focus!", text_color=WARNING)
                self._lockin_countdown_label.configure(text=f"⏱️ Auto-unlocks in {fmt_time(self.lockin_timer.remaining)}")
                self._lockin_countdown_label.pack(anchor="w", padx=18, pady=(0, 14))
            else:
                self._lockin_desc.configure(text="You are fully locked in. Focus!", text_color=WARNING)
                self._lockin_countdown_label.pack_forget()
            # Lock the mode selector while active
            self._radio_normal.configure(state="disabled")
            self._radio_timed.configure(state="disabled")
            # Fill password label
            self._password_box.configure(text=self._lock_in_password)
            self._match_label.configure(text=f"0 / {PASSWORD_LENGTH} characters typed", text_color=MUTED)
            self._match_bar.set(0)
            self._password_frame.pack(fill="x", pady=(0, 16))
            self._btn_enable_lockin.pack_forget()
        else:
            self._lockin_icon_label.configure(text="🔓")
            self._lockin_status_text.configure(text="INACTIVE", text_color=MUTED)
            self._lockin_desc.configure(text="Click Enable to enter full lock-in mode", text_color=MUTED)
            self._lockin_countdown_label.pack_forget()
            self._radio_normal.configure(state="normal")
            self._radio_timed.configure(state="normal")
            self._password_frame.pack_forget()
            self._btn_enable_lockin.pack()
            self._unlock_entry.delete(0, "end")

    def _try_unlock(self):
        entered = self._unlock_entry.get()
        if verify_password(entered, self._lock_in_password):
            if not self._confirm_early_exit():
                return  # they chose to stay locked in — entry left as-is
            if self.lockin_timer.is_running:
                self.lockin_timer.stop()
            self._lock_in_active = False
            self._lock_in_password = ""
            self._log("🔓 Lock-In Mode DISABLED.")
            self._update_lockin_ui()
            self._refresh_lockin_lists()
            self._update_stat_cards()
            self._update_status_label()
            # Remove blocks if timer is also not running
            if not self.timer.is_running:
                self._remove_active_blocks()
            messagebox.showinfo("Unlocked! 🎉", "Lock-In Mode disabled. Welcome back!")
        else:
            typed = len(entered)
            correct = sum(1 for a, b in zip(entered, self._lock_in_password) if a == b)
            self._unlock_entry.delete(0, "end")
            messagebox.showerror(
                "Wrong Password",
                f"Incorrect — {correct}/{typed} characters matched from the start.\n"
                "Check for spaces, wrong case, or missed characters. Keep going! 💪"
            )

    def _block_if_locked_in(self, action_desc: str = "change your block lists") -> bool:
        """
        Call at the top of any add/remove-from-list handler. Returns True
        (and shows a warning) if the action should be blocked because
        Lock-In Mode is active. Returns False if it's fine to proceed.
        """
        if not self._lock_in_active:
            return False
        messagebox.showwarning(
            "Locked In — Lists Are Frozen",
            f"You can't {action_desc} while Lock-In Mode is active — that's the whole point.\n\n"
            "If you genuinely need to, unlock first (Lock-In tab, password) — but ask yourself "
            "honestly first: is this actually necessary, or is it just the distraction looking "
            "for a way out? Getting distracted right now isn't worth it.",
        )
        self._log("⚠️ Blocked a list-edit attempt — Lock-In Mode is active.")
        return True

    def _confirm_early_exit(self) -> bool:
        """One last speed bump before an early, manual unlock. Returns True
        if they want to proceed with unlocking, False to stay locked in."""
        result = {"proceed": False}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Before you go...")
        dialog.geometry("440x300")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)
        dialog.grab_set()
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 440) // 2
        y = self.winfo_y() + (self.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="🤔", font=("Segoe UI", 34)).pack(pady=(18, 4))
        ctk.CTkLabel(dialog, text="You typed the password correctly.",
                     font=FONT_H3, text_color=TEXT).pack()
        ctk.CTkLabel(
            dialog, text=random_rethink_quote(),
            font=("Segoe UI", 12), text_color=MUTED, justify="center", wraplength=380,
        ).pack(pady=(10, 4), padx=20)
        ctk.CTkLabel(
            dialog, text="If something's genuinely urgent, that's completely fine — go ahead.",
            font=("Segoe UI", 11), text_color=MUTED, justify="center",
        ).pack(pady=(0, 16))

        def choose(v):
            result["proceed"] = v
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="Stay Locked In", width=170, height=38, corner_radius=10,
                       fg_color=SUCCESS, hover_color="#16A34A", font=FONT_BODY,
                       command=lambda: choose(False)).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="It's Urgent — Exit", width=160, height=38, corner_radius=10,
                       fg_color=DANGER, hover_color="#DC2626", font=FONT_BODY,
                       command=lambda: choose(True)).pack(side="left", padx=6)

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(False))
        self.wait_window(dialog)
        return result["proceed"]

    # ── Blocking helpers ──────────────────────────────────────────────────────

    def _is_blocking_active(self) -> bool:
        return self.timer.is_running or self._lock_in_active

    def _apply_active_blocks(self) -> None:
        """Apply website + app blocks (called when timer starts or lock-in enables)."""
        self.app_blocker.set_blocked_apps(self.config_data["blocked_apps"])
        # Activate title-based website blocking (no hosts file — works in all browser modes)
        sites = self.config_data.get("blocked_websites", [])
        self.keyword_blocker.set_active_blocked_sites(sites)
        self._log(f"🔒 Blocking activated — {len(sites)} site(s) and apps now blocked.")
        # Start (or continue) the stats session clock — only set once, so
        # stacking timer + lock-in together doesn't reset the running total.
        if self._active_session_start is None:
            self._active_session_start = time.time()
            self._stats_checkpoint = self._active_session_start

    def _remove_active_blocks(self) -> None:
        """Remove all blocks (called when timer stops AND lock-in is off)."""
        self.app_blocker.set_blocked_apps([])
        self.keyword_blocker.set_active_blocked_sites([])
        self._log("✅ Blocking deactivated — websites and apps are accessible again.")
        # Finalize this session's elapsed time into the stats log. Most of
        # it has already been periodically checkpointed (see
        # _periodic_stats_tick), so only the time since the last checkpoint
        # needs to be flushed here.
        if self._active_session_start is not None:
            checkpoint_from = self._stats_checkpoint or self._active_session_start
            elapsed = time.time() - checkpoint_from
            stats_manager.add_focused_seconds(elapsed)
            self._active_session_start = None
            self._stats_checkpoint = None
            self._refresh_stats_page()

    def _update_status_label(self) -> None:
        if self._lock_in_active:
            self._status_label.configure(text="🔒 Lock-In active", text_color=DANGER)
        elif self.timer.is_running:
            self._status_label.configure(text="⏱️ Timer running — blocking on", text_color=SUCCESS)
        else:
            self._status_label.configure(text="○ No active session", text_color=MUTED)

    # ── Keyword detected callback ─────────────────────────────────────────────

    def _on_keyword_detected(self, keyword: str, source: str, quote: str) -> None:
        """Called from background thread — schedule UI update on main thread."""
        self.after(0, lambda: self._log(
            f"🔑 Keyword '{keyword}' detected in {source}. Reminder sent."
        ))

    # ── Keywords page ─────────────────────────────────────────────────────────

    def _build_keywords_page(self):
        f = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent",
                                    scrollbar_button_color=BG_CARD)
        self._content_frames["Keywords"] = f

        ctk.CTkLabel(f, text="Keyword Blocker", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f,
                     text="Always active — closes the browser tab the moment a blocked keyword appears\n"
                          "in the page title/content, no timer needed. Outside the browser (or on the\n"
                          "clipboard) it sends a notification with a motivational quote instead.",
                     font=FONT_BODY, text_color=MUTED, justify="left").pack(anchor="w", pady=(4, 20))

        # How it works card
        how_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        how_card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(how_card, text="How it works", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        steps = [
            ("🔍", "Watches your active window title every 0.5 seconds, plus real page\n     content via the browser extension (catches whole-word matches only,\n     e.g. 'car' won't trip on 'scary' or 'career')"),
            ("🗙",  "Browser tab open + keyword found → tab is closed immediately"),
            ("📋", "Watches your clipboard for copied text containing keywords"),
            ("🔔", "Sends a desktop notification + motivational quote when detected"),
            ("⏻",  "Always running — independent of timer and lock-in mode"),
        ]
        for icon, text in steps:
            row = ctk.CTkFrame(how_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=icon, font=("Segoe UI", 18), width=30).pack(side="left")
            ctk.CTkLabel(row, text=text, font=("Segoe UI", 12), text_color=MUTED,
                         justify="left").pack(side="left", padx=8)
        ctk.CTkFrame(how_card, height=1, fg_color="#334155").pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(how_card,
                     text="💡 Tip: Add words like 'porn', 'reddit', 'tiktok', 'netflix' to stay focused.",
                     font=("Segoe UI", 12), text_color=WARNING).pack(anchor="w", padx=16, pady=(8, 14))

        # Adult content filter — opt-in, off by default
        adult_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        adult_card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(adult_card, text="Adult Content Filter", font=FONT_H3,
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            adult_card,
            text="Off by default, so it doesn't get in anyone's way unasked. Turn it\n"
                 "on if you want a built-in list of adult-site terms closed on sight —\n"
                 "your own custom keywords below stay active either way.",
            font=("Segoe UI", 12), text_color=MUTED, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self._adult_content_var = ctk.BooleanVar(value=self.config_data.get("block_adult_content", False))
        ctk.CTkSwitch(
            adult_card, text="Block adult content", variable=self._adult_content_var,
            onvalue=True, offvalue=False, font=FONT_BODY,
            command=self._on_toggle_adult_content,
        ).pack(anchor="w", padx=16, pady=(0, 14))

        # Add keyword input
        ctk.CTkLabel(f, text="Blocked Keywords", font=FONT_H2, text_color=TEXT).pack(anchor="w", pady=(0, 10))

        input_row = ctk.CTkFrame(f, fg_color="transparent")
        input_row.pack(fill="x", pady=(0, 12))
        self._kw_entry = ctk.CTkEntry(input_row, placeholder_text="e.g. porn, tiktok, reddit",
                                       height=44, font=FONT_BODY, fg_color=BG_CARD,
                                       corner_radius=10, border_width=0)
        self._kw_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._kw_entry.bind("<Return>", lambda e: self._add_keyword())
        ctk.CTkButton(input_row, text="+ Add", height=44, width=100, corner_radius=10,
                       fg_color=ACCENT, hover_color="#2563EB", font=FONT_BODY,
                       command=self._add_keyword).pack(side="left")

        ctk.CTkLabel(f, text="Each keyword is checked case-insensitively as a whole word (e.g. 'car' won't match 'scary' or 'card').",
                     font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", pady=(0, 10))

        # Keyword list
        self._kw_list_frame = ctk.CTkScrollableFrame(f, fg_color=BG_CARD, corner_radius=12,
                                                      scrollbar_button_color=BG_MAIN)
        self._kw_list_frame.pack(fill="both", expand=True)

        self._refresh_keyword_list()

    def _add_keyword(self):
        # Adding is allowed even during Lock-In — only removing is frozen.
        kw = self._kw_entry.get().strip().lower()
        if not kw:
            return
        keywords = self.config_data.setdefault("blocked_keywords", [])
        if kw not in keywords:
            keywords.append(kw)
            save_config(self.config_data)
            self.keyword_blocker.set_keywords(keywords)
            self._kw_entry.delete(0, "end")
            self._refresh_keyword_list()
            self._log(f"🔑 Added keyword: '{kw}' — always active")

    def _on_toggle_adult_content(self):
        enabled = self._adult_content_var.get()
        if self._lock_in_active and not enabled:
            # Same "add, don't remove" rule as the block lists — turning
            # the filter ON during Lock-In is fine (that's strengthening
            # things), but turning it OFF would be a way to weasel out of
            # a restriction mid-session, so that's frozen until unlock.
            self._adult_content_var.set(True)
            messagebox.showwarning(
                "Locked In — Filter Can't Be Turned Off",
                "You can't disable adult content blocking while Lock-In Mode is "
                "active. Unlock first (Lock-In tab, password) if this is "
                "genuinely necessary.",
            )
            self._log("⚠️ Blocked an attempt to disable adult content blocking — Lock-In Mode is active.")
            return
        self.config_data["block_adult_content"] = enabled
        save_config(self.config_data)
        self.keyword_blocker.set_adult_content_blocking(enabled)
        self._log("🔞 Adult content blocking enabled." if enabled else "Adult content blocking turned off.")

    def _remove_keyword(self, kw: str):
        if self._block_if_locked_in("remove keywords from your blocked-keywords list"):
            return
        keywords = self.config_data.get("blocked_keywords", [])
        if kw in keywords:
            keywords.remove(kw)
            save_config(self.config_data)
            self.keyword_blocker.set_keywords(keywords)
            self._refresh_keyword_list()
            self._log(f"Removed keyword: '{kw}'")

    def _refresh_keyword_list(self):
        for w in self._kw_list_frame.winfo_children():
            w.destroy()
        keywords = self.config_data.get("blocked_keywords", [])
        if not keywords:
            ctk.CTkLabel(self._kw_list_frame, text="No keywords added yet. Add one above.",
                         font=FONT_BODY, text_color=MUTED).pack(pady=30)
            return
        for kw in keywords:
            row = ctk.CTkFrame(self._kw_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=f"🔑  {kw}", font=FONT_BODY, text_color=TEXT).pack(side="left")
            ctk.CTkLabel(row, text="always active", font=("Segoe UI", 11),
                         text_color=SUCCESS).pack(side="left", padx=14)
            ctk.CTkButton(row, text="Remove", width=80, height=30, corner_radius=8,
                           fg_color=DANGER, hover_color="#DC2626", font=("Segoe UI", 12),
                           command=lambda k=kw: self._remove_keyword(k)).pack(side="right")

    # ── Stats page ───────────────────────────────────────────────────────────

    def _build_stats_page(self):
        f = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent",
                                    scrollbar_button_color=BG_CARD)
        self._content_frames["Stats"] = f
        self._stats_frame = f

        ctk.CTkLabel(f, text="Stats", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="How much time you've protected from distractions.",
                     font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 20))

        # ── Summary cards row ────────────────────────────────────────────────
        cards_row = ctk.CTkFrame(f, fg_color="transparent")
        cards_row.pack(fill="x", pady=(0, 20))

        self._stats_cards = {}
        card_defs = [("today", "Today", "🔥"), ("week", "This Week", "📅"),
                     ("month", "This Month", "🗓️"), ("year", "This Year", "📈"),
                     ("all_time", "All-Time", "🏆")]
        for key, label, emoji in card_defs:
            card = ctk.CTkFrame(cards_row, fg_color=BG_CARD, corner_radius=14)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10))
            ctk.CTkLabel(card, text=emoji, font=("Segoe UI", 20)).pack(pady=(14, 2))
            value_label = ctk.CTkLabel(card, text="0s", font=("Segoe UI", 18, "bold"), text_color=TEXT)
            value_label.pack()
            ctk.CTkLabel(card, text=label, font=("Segoe UI", 11), text_color=MUTED).pack(pady=(0, 14))
            self._stats_cards[key] = value_label

        # ── Daily breakdown (last 14 days) ──────────────────────────────────
        daily_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        daily_card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(daily_card, text="Daily — last 14 days", font=FONT_H3, text_color=TEXT).pack(
            anchor="w", padx=16, pady=(14, 8))
        self._daily_list_frame = ctk.CTkFrame(daily_card, fg_color="transparent")
        self._daily_list_frame.pack(fill="x", padx=16, pady=(0, 14))

        # ── Monthly breakdown ────────────────────────────────────────────────
        monthly_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        monthly_card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(monthly_card, text="Monthly — last 12 months", font=FONT_H3, text_color=TEXT).pack(
            anchor="w", padx=16, pady=(14, 8))
        self._monthly_list_frame = ctk.CTkFrame(monthly_card, fg_color="transparent")
        self._monthly_list_frame.pack(fill="x", padx=16, pady=(0, 14))

        # ── Yearly breakdown ─────────────────────────────────────────────────
        yearly_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        yearly_card.pack(fill="x")
        ctk.CTkLabel(yearly_card, text="Yearly", font=FONT_H3, text_color=TEXT).pack(
            anchor="w", padx=16, pady=(14, 8))
        self._yearly_list_frame = ctk.CTkFrame(yearly_card, fg_color="transparent")
        self._yearly_list_frame.pack(fill="x", padx=16, pady=(0, 14))

    def _current_session_elapsed(self) -> float:
        """Extra elapsed time from a session that's still in progress right
        now, not yet written to disk (so 'Today' updates live). This is
        measured from the last periodic checkpoint, not from session
        start, since everything before the checkpoint is already on disk."""
        if self._active_session_start is None:
            return 0.0
        checkpoint_from = self._stats_checkpoint or self._active_session_start
        return time.time() - checkpoint_from

    def _refresh_stats_page(self):
        if not hasattr(self, "_stats_cards"):
            return  # page not built yet

        summary = stats_manager.get_summary()
        live_extra = self._current_session_elapsed()

        self._stats_cards["today"].configure(text=stats_manager.format_duration(summary["today"] + live_extra))
        self._stats_cards["week"].configure(text=stats_manager.format_duration(summary["week"] + live_extra))
        self._stats_cards["month"].configure(text=stats_manager.format_duration(summary["month"] + live_extra))
        self._stats_cards["year"].configure(text=stats_manager.format_duration(summary["year"] + live_extra))
        self._stats_cards["all_time"].configure(text=stats_manager.format_duration(summary["all_time"] + live_extra))

        # Daily rows
        for child in self._daily_list_frame.winfo_children():
            child.destroy()
        max_daily = max((v for _, v in summary["last_14_days"]), default=0) or 1
        today_iso = date.today().isoformat()
        for day_iso, seconds in summary["last_14_days"]:
            shown = seconds + (live_extra if day_iso == today_iso else 0)
            self._stats_bar_row(self._daily_list_frame, day_iso[5:], shown, max_daily)

        # Monthly rows
        for child in self._monthly_list_frame.winfo_children():
            child.destroy()
        if summary["monthly"]:
            max_monthly = max(v for _, v in summary["monthly"]) or 1
            for month_key, seconds in summary["monthly"]:
                yr, mo = month_key.split("-")
                label = f"{stats_manager.MONTH_NAMES[int(mo) - 1]} {yr}"
                self._stats_bar_row(self._monthly_list_frame, label, seconds, max_monthly)
        else:
            ctk.CTkLabel(self._monthly_list_frame, text="No sessions yet.",
                         font=("Segoe UI", 12), text_color=MUTED).pack(anchor="w")

        # Yearly rows
        for child in self._yearly_list_frame.winfo_children():
            child.destroy()
        if summary["yearly"]:
            max_yearly = max(v for _, v in summary["yearly"]) or 1
            for year, seconds in summary["yearly"]:
                self._stats_bar_row(self._yearly_list_frame, str(year), seconds, max_yearly)
        else:
            ctk.CTkLabel(self._yearly_list_frame, text="No sessions yet.",
                         font=("Segoe UI", 12), text_color=MUTED).pack(anchor="w")

    def _stats_bar_row(self, parent, label: str, seconds: float, max_seconds: float):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 11), text_color=MUTED, width=70,
                     anchor="w").pack(side="left")
        bar_bg = ctk.CTkFrame(row, fg_color="#0F172A", height=14, corner_radius=7)
        bar_bg.pack(side="left", fill="x", expand=True, padx=(6, 8))
        frac = min(1.0, seconds / max_seconds) if max_seconds else 0
        if frac > 0:
            bar_fill = ctk.CTkFrame(bar_bg, fg_color=ACCENT, height=14, corner_radius=7,
                                     width=max(6, int(frac * 260)))
            bar_fill.place(x=0, y=0)
        ctk.CTkLabel(row, text=stats_manager.format_duration(seconds), font=("Segoe UI", 11),
                     text_color=TEXT, width=60, anchor="e").pack(side="left")

    def _periodic_stats_tick(self):
        """Keep 'Today' live while a session is running and the Stats tab is
        open, AND periodically checkpoint the elapsed time to disk. Stats
        used to only be saved when a session ended cleanly (timer stopped /
        Lock-In unlocked) — if the app was killed or crashed instead
        (e.g. a stuck background process with no visible window or tray
        icon), that entire session's time was silently lost. Flushing every
        5 seconds means at most ~5s is ever at risk."""
        if self._active_session_start is not None:
            now = time.time()
            checkpoint_from = self._stats_checkpoint or self._active_session_start
            elapsed = now - checkpoint_from
            if elapsed > 0:
                stats_manager.add_focused_seconds(elapsed)
                self._stats_checkpoint = now
            current = self._content_frames.get("Stats")
            if current is not None and current.winfo_ismapped():
                self._refresh_stats_page()
        self.after(5000, self._periodic_stats_tick)

    # ── Settings page ────────────────────────────────────────────────────────

    def _build_settings_page(self):
        f = ctk.CTkScrollableFrame(self._content_area, fg_color="transparent",
                                    scrollbar_button_color=BG_CARD)
        self._content_frames["Settings"] = f

        ctk.CTkLabel(f, text="Settings", font=FONT_H1, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(f, text="App-wide preferences.",
                     font=FONT_BODY, text_color=MUTED).pack(anchor="w", pady=(4, 20))

        card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(card, text="Startup", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 4))

        if platform.system() != "Windows":
            ctk.CTkLabel(
                card,
                text="Launch-at-startup is only available on Windows. This machine is running "
                     f"{platform.system()}.",
                font=("Segoe UI", 12), text_color=MUTED, justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 14))
        else:
            ctk.CTkLabel(
                card,
                text="Start FocusGuardian automatically whenever you log into Windows —\n"
                     "no need to remember to open it yourself.",
                font=("Segoe UI", 12), text_color=MUTED, justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 10))

            self._startup_var = ctk.BooleanVar(value=is_startup_enabled())
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(0, 14))
            self._startup_switch = ctk.CTkSwitch(
                row, text="Launch when Windows starts",
                variable=self._startup_var, onvalue=True, offvalue=False,
                font=FONT_BODY, command=self._on_toggle_startup,
            )
            self._startup_switch.pack(side="left")
            self._startup_status_label = ctk.CTkLabel(
                row, text="", font=("Segoe UI", 11), text_color=SUCCESS
            )
            self._startup_status_label.pack(side="left", padx=12)

        about = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        about.pack(fill="x")
        ctk.CTkLabel(about, text="About", font=FONT_H3, text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            about, text="FocusGuardian — website, app, and keyword blocker for staying focused.",
            font=("Segoe UI", 12), text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(0, 14))

        ctk.CTkLabel(about, text="Made by Alok Pandey", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(
            about,
            text="Solo dev — mostly vibe-coding this with a bit of hand-written code\n"
                 "sprinkled in. Still leveling up at this, aiming to build bigger things\n"
                 "fully by myself down the line. Stay tuned.",
            font=("Segoe UI", 12), text_color=MUTED, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        links_row = ctk.CTkFrame(about, fg_color="transparent")
        links_row.pack(anchor="w", padx=16, pady=(0, 4))

        github_link = ctk.CTkLabel(
            links_row, text="GitHub ↗", font=("Segoe UI", 12, "underline"),
            text_color=ACCENT, cursor="hand2",
        )
        github_link.pack(side="left", padx=(0, 18))
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/alokpandey0803"))

        linkedin_link = ctk.CTkLabel(
            links_row, text="LinkedIn ↗", font=("Segoe UI", 12, "underline"),
            text_color=ACCENT, cursor="hand2",
        )
        linkedin_link.pack(side="left")
        linkedin_link.bind(
            "<Button-1>",
            lambda e: webbrowser.open("https://www.linkedin.com/in/alok-pandey-609259378/"),
        )

        ctk.CTkLabel(
            about, text="💬 Feel free to connect with me on LinkedIn!",
            font=("Segoe UI", 12), text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(6, 14))

        disclaimer = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=14)
        disclaimer.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(disclaimer, text="A Note on Limitations", font=FONT_H3,
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            disclaimer,
            text="This is a solo project, so it won't be 100% perfect — bugs happen.\n"
                 "And even a flawless blocker can't do the one thing that actually\n"
                 "matters: if you don't have the willpower to stick with it, you'll\n"
                 "find a way around it. This app can only make distraction a little\n"
                 "more inconvenient — the rest is on you.",
            font=("Segoe UI", 12), text_color=MUTED, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 14))

        ctk.CTkFrame(disclaimer, height=1, fg_color="#334155").pack(fill="x", padx=16)
        ctk.CTkLabel(
            disclaimer,
            text="Feel free to use, learn from, and modify this — just don't strip\n"
                 "this section out and pass it off as your own work. Claiming\n"
                 "someone else's project as yours is a bad habit to get into,\n"
                 "and it catches up with you eventually. Credit costs nothing.",
            font=("Segoe UI", 12), text_color=MUTED, justify="left",
        ).pack(anchor="w", padx=16, pady=(10, 14))

    def _on_toggle_startup(self):
        want_on = self._startup_var.get()
        ok = enable_startup() if want_on else disable_startup()
        if ok:
            self._startup_status_label.configure(
                text="✅ Enabled" if want_on else "Disabled",
                text_color=SUCCESS if want_on else MUTED,
            )
            self._log(f"{'Enabled' if want_on else 'Disabled'} launch-at-startup.")
        else:
            # Revert the switch since the registry write failed
            self._startup_var.set(not want_on)
            self._startup_switch.deselect() if not want_on else self._startup_switch.select()
            messagebox.showerror(
                "Couldn't update startup setting",
                "FocusGuardian couldn't write to the Windows startup registry key. "
                "Try running the app as your normal user (not via an admin-restricted account).",
            )

    # ── Close guard ───────────────────────────────────────────────────────────

    def _on_close(self):
        if self._lock_in_active:
            # Can't fully exit, but no need to force the window to stay open
            # either — let it drop to the tray. The password is still
            # required for a real exit (enforced in _handle_tray_exit_request).
            self._minimize_to_tray()
            send_notification(
                "🔒 Still Locked In",
                "FocusGuardian is running in the background. Type the\n"
                "password on the Lock-In tab whenever you want to fully exit.",
            )
            return
        choice = self._ask_close_behavior()
        if choice == "background":
            self._minimize_to_tray()
        elif choice == "exit":
            self._shutdown()
        # choice is None (Cancel / dialog closed) → do nothing, window stays open

    def _ask_close_behavior(self) -> str | None:
        """Small modal: Run in Background / Exit App / Cancel. Returns the choice."""
        result = {"choice": None}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Close FocusGuardian")
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)
        dialog.grab_set()
        # Center over the main window
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 230) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="🔒", font=("Segoe UI", 34)).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="What would you like to do?", font=FONT_H3, text_color=TEXT).pack()
        ctk.CTkLabel(
            dialog,
            text="Blocking keeps running either way — this only decides\n"
                 "whether the window/taskbar icon disappears.",
            font=("Segoe UI", 11), text_color=MUTED, justify="center",
        ).pack(pady=(6, 16))

        def choose(c):
            result["choice"] = c
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="Run in Background", width=170, height=38, corner_radius=10,
                       fg_color=ACCENT, hover_color="#2563EB", font=FONT_BODY,
                       command=lambda: choose("background")).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Exit App", width=110, height=38, corner_radius=10,
                       fg_color=DANGER, hover_color="#DC2626", font=FONT_BODY,
                       command=lambda: choose("exit")).pack(side="left", padx=6)
        ctk.CTkButton(dialog, text="Cancel", width=100, height=32, corner_radius=8,
                       fg_color="transparent", hover_color="#334155", text_color=MUTED,
                       font=("Segoe UI", 12),
                       command=lambda: choose(None)).pack(pady=(14, 0))

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self.wait_window(dialog)
        return result["choice"]

    def _minimize_to_tray(self):
        """Hide the window and taskbar entry; keep blocking running via the tray icon."""
        self.withdraw()
        self._tray.show()
        self._log("🫥 Running in background — right-click the tray icon to reopen or exit.")

    def _tray_restore(self):
        """Called from the pystray thread — marshal back onto the Tk main loop."""
        self.after(0, self._do_tray_restore)

    def _bring_to_front(self):
        """Force the window above other apps — using the standard
        topmost-then-untopmost trick, since a plain lift()/focus_force()
        is sometimes ignored by Windows if another app currently has focus."""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    def _do_tray_restore(self):
        self._tray.hide()
        self._bring_to_front()

    def _external_show_request(self):
        """Called (via .after(0, ...)) when a second launch attempt of the
        app detects we're already running and asks us to come to the
        foreground, instead of starting a duplicate process. This is what
        makes 'opening the app again' always reach this one real instance
        rather than spawning a second, independent copy that keeps
        blocking in the background with no way to see or control it."""
        if self.state() == "withdrawn":
            self._do_tray_restore()
        else:
            self._bring_to_front()

    def _tray_exit(self):
        """Called from the pystray thread — marshal back onto the Tk main loop."""
        self.after(0, self._handle_tray_exit_request)

    def _handle_tray_exit_request(self):
        if self._lock_in_active:
            # Bring the app back and make them go through the real unlock
            # flow — no exiting Lock-In from the tray menu.
            self._tray.hide()
            self._bring_to_front()
            self._switch_tab("Lock-In")
            messagebox.showerror(
                "Locked In!",
                "Lock-In Mode is active.\nType the password on the Lock-In tab to exit.",
            )
            return
        self._shutdown()

    def _shutdown(self):
        """Actually stop everything and close the app for good."""
        self.timer.stop()       # previously never stopped on exit
        self.lockin_timer.stop()
        # Finalize whatever's left of the current session into stats.json
        # (previously skipped entirely on exit, so quitting while the
        # study timer — not Lock-In — was running silently discarded that
        # session's time) and clear blocking state.
        self._remove_active_blocks()
        self.app_blocker.stop()
        self.keyword_blocker.stop()
        self._tray.hide()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _install_crash_logger():
        """The packaged exe runs with no console window, so an unhandled
        exception would otherwise just vanish — no error message, no way
        to know why it closed. This writes a plain-text log instead, so a
        crash can actually be diagnosed/reported."""
        import datetime
        log_path = os.path.join(app_paths.data_dir(), "crash.log")

        def _handle_exception(exc_type, exc_value, exc_tb):
            try:
                import traceback
                with open(log_path, "a") as f:
                    f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
                    traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            except Exception:
                pass
            sys.__excepthook__(exc_type, exc_value, exc_tb)

        sys.excepthook = _handle_exception

    _install_crash_logger()

    # Holds the app instance once created, so the single-instance socket
    # handler (which fires on a background thread, possibly before the Tk
    # app object exists yet) can safely find it and marshal onto the main
    # loop.
    _app_holder: dict = {}

    def _handle_show_request():
        app_ref = _app_holder.get("app")
        if app_ref is not None:
            app_ref.after(0, app_ref._external_show_request)

    _instance_lock = SingleInstance(on_show_requested=_handle_show_request)
    if not _instance_lock.try_acquire():
        # Another copy of FocusGuardian is already running — it's just
        # been signalled to bring its window to the front. Exit here
        # instead of starting a second, independent instance (which would
        # keep its own timer/blocker state running invisibly).
        sys.exit(0)

    app = StudyBlockerApp()
    _app_holder["app"] = app
    app.mainloop()
