import tkinter as tk
from tkinter import ttk, messagebox
import feedparser
import webbrowser
from datetime import datetime
import time
import threading
import pystray
from PIL import Image, ImageDraw
import platform
import json
import os
import sys

SETTINGS_FILE = "rss_reader_settings.json"
RSS_FEED_URL = "https://plugindealz.com/board/rss.php"

class SimpleRSSReader:
    def __init__(self, root):
        self.root = root
        self.root.title("Plugin Deals Notifier")
        self.root.geometry("600x500")

        self.entries = []
        self.current_titles = set()

        self.load_settings()
        self.create_widgets()
        self.load_feed()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.refresh_id = None
        self.schedule_refresh()

        threading.Thread(target=self.setup_tray_icon, daemon=True).start()

    def create_widgets(self):
        frame_top = tk.Frame(self.root)
        frame_top.pack(fill="x", padx=10, pady=5)

        # First row
        frame_top1 = tk.Frame(frame_top)
        frame_top1.pack(fill="x")

        tk.Label(frame_top1, text="Auto-refresh interval (minutes):").pack(side="left")
        self.interval_entry = ttk.Entry(frame_top1, width=6)
        self.interval_entry.pack(side="left", padx=(5, 10))
        self.interval_entry.insert(0, str(self.settings.get("refresh_interval_minutes", 5)))

        self.set_interval_btn = ttk.Button(frame_top1, text="Set", command=self.set_refresh_interval)
        self.set_interval_btn.pack(side="left", padx=(0, 20))

        # Second row
        frame_top2 = tk.Frame(frame_top)
        frame_top2.pack(fill="x", pady=(5, 0))

        tk.Label(frame_top2, text="Notifier:").pack(side="left")
        self.notifier_var = tk.StringVar(value=self.settings.get("notifier_type", "all"))
        notifier_all = ttk.Radiobutton(frame_top2, text="All Deals", variable=self.notifier_var, value="all")
        notifier_all.pack(side="left", padx=5)
        notifier_kw = ttk.Radiobutton(frame_top2, text="Deals containing keywords:", variable=self.notifier_var, value="keywords")
        notifier_kw.pack(side="left", padx=5)

        self.keywords_entry = ttk.Entry(frame_top2, width=30)
        self.keywords_entry.pack(side="left", padx=(5, 5))
        self.keywords_entry.insert(0, self.settings.get("keywords", ""))

        self.set_keywords_btn = ttk.Button(frame_top2, text="Set", command=self.set_keywords)
        self.set_keywords_btn.pack(side="left", padx=5)

        # Third row (new row for the two checkbuttons)
        frame_top3 = tk.Frame(frame_top)
        frame_top3.pack(fill="x", pady=(5, 0))

        self.load_startup_var = tk.BooleanVar(value=self.settings.get("load_on_startup", False))
        self.load_startup_cb = ttk.Checkbutton(frame_top3, text="Load on startup", variable=self.load_startup_var, command=self.set_load_on_startup)
        self.load_startup_cb.pack(side="left", padx=15)

        self.disable_notifications_var = tk.BooleanVar(value=self.settings.get("disable_notifications", False))
        self.disable_notifications_cb = ttk.Checkbutton(
            frame_top3,
            text="Disable notifications",
            variable=self.disable_notifications_var,
            command=self.toggle_notifications
        )
        self.disable_notifications_cb.pack(side="left", padx=10)

        # Listbox
        self.listbox = tk.Listbox(self.root, font=("Segoe UI", 11))
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.listbox.bind("<Double-1>", self.open_entry)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        self.status_label = tk.Label(bottom_frame, text="Last updated: --:--:--", anchor="w")
        self.status_label.pack(side="left")

        self.refresh_button = ttk.Button(bottom_frame, text="Refresh Now", command=self.load_feed)
        self.refresh_button.pack(side="right")

    def toggle_notifications(self):
        self.settings["disable_notifications"] = self.disable_notifications_var.get()
        self.save_settings()

    def set_refresh_interval(self):
        try:
            val = int(self.interval_entry.get())
            if val < 1 or val > 1440:
                messagebox.showerror("Invalid interval", "Please enter a value between 1 and 1440.")
                return
            self.settings["refresh_interval_minutes"] = val
            self.save_settings()
            self.schedule_refresh()
            messagebox.showinfo("Refresh interval set", f"Auto-refresh interval set to {val} minute(s).")
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter a valid integer.")

    def set_keywords(self):
        self.settings["keywords"] = self.keywords_entry.get()
        self.settings["notifier_type"] = self.notifier_var.get()
        self.save_settings()
        self.load_feed()

    def set_load_on_startup(self):
        val = self.load_startup_var.get()
        self.settings["load_on_startup"] = val
        self.save_settings()
        self.configure_startup(val)

    def configure_startup(self, enable):
        if platform.system() != "Windows":
            messagebox.showinfo("Not supported", "Load on startup is only supported on Windows.")
            return

        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        shortcut_path = os.path.join(startup_dir, "PluginDealsNotifier.lnk")

        if enable:
            python_exe = sys.executable.replace("\\", "\\\\")
            script_path = os.path.abspath(sys.argv[0]).replace("\\", "\\\\")
            working_dir = os.path.dirname(script_path).replace("\\", "\\\\")

            vbs_content = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{python_exe}"
oLink.Arguments = "{script_path}"
oLink.WorkingDirectory = "{working_dir}"
oLink.WindowStyle = 1
oLink.IconLocation = "{python_exe}, 0"
oLink.Description = "Plugin Deals Notifier"
oLink.Save
'''

            vbs_path = os.path.join(os.getenv('TEMP'), "create_shortcut.vbs")
            try:
                with open(vbs_path, "w") as f:
                    f.write(vbs_content)
                os.system(f'cscript //nologo "{vbs_path}"')
                os.remove(vbs_path)
                messagebox.showinfo("Startup Enabled", "The app will now load on Windows startup.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create startup shortcut:\n{e}")
        else:
            try:
                if os.path.isfile(shortcut_path):
                    os.remove(shortcut_path)
                messagebox.showinfo("Startup Disabled", "The app will no longer load on Windows startup.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to remove startup shortcut:\n{e}")

    def schedule_refresh(self):
        if self.refresh_id:
            self.root.after_cancel(self.refresh_id)
        ms = self.settings.get("refresh_interval_minutes", 5) * 60 * 1000
        self.refresh_id = self.root.after(ms, self.refresh_feed)

    def load_settings(self):
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    self.settings = json.load(f)
            except Exception:
                self.settings = {}
        else:
            self.settings = {}

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f)
        except Exception as e:
            print("Error saving settings:", e)

    def load_feed(self):
        feed = feedparser.parse(RSS_FEED_URL)
        new_entries = feed.entries
        today_str = datetime.now().strftime("%Y-%m-%d")

        if self.settings.get("notifier_type", "all") == "keywords":
            keywords = [k.strip().lower() for k in self.settings.get("keywords", "").split(",") if k.strip()]
            if keywords:
                filtered_entries = []
                for entry in new_entries:
                    content_to_check = (entry.title + " " + getattr(entry, "summary", "")).lower()
                    if any(k in content_to_check for k in keywords):
                        filtered_entries.append(entry)
                filtered = filtered_entries
            else:
                filtered = new_entries
        else:
            filtered = new_entries

        new_titles = set(entry.title for entry in filtered)
        is_new_content = new_titles != self.current_titles
        self.current_titles = new_titles

        self.entries = filtered
        self.listbox.delete(0, tk.END)

        for i, entry in enumerate(self.entries):
            title_to_display = entry.title
            if hasattr(entry, "published_parsed"):
                pub_date = datetime(*entry.published_parsed[:6])
                if pub_date.strftime("%Y-%m-%d") == today_str:
                    title_to_display = "[new] " + title_to_display
            self.listbox.insert(tk.END, title_to_display)

        self.update_status_label()

        if is_new_content:
            self.notify_new_content()

    def refresh_feed(self):
        self.load_feed()
        self.schedule_refresh()

    def update_status_label(self):
        now = time.strftime("%H:%M:%S")
        self.status_label.config(text=f"Last updated: {now}")

    def notify_new_content(self):
        if self.settings.get("disable_notifications", False):
            return
        if hasattr(self, 'tray_icon'):
            if platform.system() in ['Windows', 'Linux']:
                self.tray_icon.notify("New deals!", "New items found in the feed.")

    def open_entry(self, event):
        sel = self.listbox.curselection()
        if sel:
            entry = self.entries[sel[0]]
            webbrowser.open(entry.link)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        icon.stop()
        self.root.destroy()

    def setup_tray_icon(self):
        icon_image = Image.new('RGB', (64, 64), color=(0, 0, 0))
        draw = ImageDraw.Draw(icon_image)
        draw.rectangle([0, 0, 63, 63], fill='blue')
        draw.text((8, 20), "PD", fill="white")

        menu = pystray.Menu(
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Refresh", lambda icon, item: self.load_feed()),
            pystray.MenuItem("Quit", self.quit_app)
        )

        self.tray_icon = pystray.Icon("PluginDealsNotifier", icon_image, "Plugin Deals Notifier", menu)
        self.tray_icon.run()

def main():
    root = tk.Tk()
    app = SimpleRSSReader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
