"""Shared graphical installer for the macOS and Linux release packages.

The operating systems use different package formats, but this small bundled
application keeps the human-facing installation journey consistent with the
Windows Inno Setup wizard: welcome, licence, location, shortcut, confirmation,
progress, and completion.  It deliberately installs only into a safe,
user-approved location and never removes anything outside its own target.
"""
from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

APP_NAME = "Scientific Calculator"
APP_BUNDLE_NAME = f"{APP_NAME}.app"
UNINSTALLER_NAME = f"{APP_NAME} Uninstaller.app"


def _resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    return Path(bundled_root) if bundled_root else Path(__file__).resolve().parent


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _default_install_root() -> Path:
    return Path("/Applications") if _is_macos() else Path.home() / ".local" / "opt"


def _app_name_for_platform() -> str:
    return APP_BUNDLE_NAME if _is_macos() else "ScientificCalculator"


def _safe_install_target(root: Path) -> Path:
    """Return the fixed app-owned child when the selected root is safe."""
    resolved_root = root.expanduser().resolve()
    home = Path.home().resolve()
    if _is_macos():
        allowed_roots = {Path("/Applications"), home / "Applications"}
        if resolved_root not in allowed_roots:
            raise ValueError("Choose /Applications or your ~/Applications folder.")
    elif resolved_root != home and home not in resolved_root.parents:
        raise ValueError("Linux installs must stay inside your home folder.")
    return resolved_root / _app_name_for_platform()


class SetupWizard:
    def __init__(self) -> None:
        self.resources = _resource_root()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Setup Wizard")
        self.root.geometry("680x510")
        self.root.minsize(680, 510)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self.install_root = tk.StringVar(value=str(_default_install_root()))
        self.create_shortcut = tk.BooleanVar(value=True)
        self.launch_after_install = tk.BooleanVar(value=True)
        self.accepted_license = tk.BooleanVar(value=False)
        self.page = 0
        self._side_image: ImageTk.PhotoImage | None = None

        self._build_layout()
        self._show_page(0)

    def _build_layout(self) -> None:
        self.content = ttk.Frame(self.root, padding=(26, 20))
        self.content.pack(fill="both", expand=True)
        self.navigation = ttk.Frame(self.root, padding=(12, 10))
        self.navigation.pack(fill="x", side="bottom")
        self.back_button = ttk.Button(self.navigation, text="Back", command=self._back)
        self.back_button.pack(side="right", padx=(0, 8))
        self.next_button = ttk.Button(self.navigation, text="Next", command=self._next)
        self.next_button.pack(side="right", padx=(0, 8))
        ttk.Button(self.navigation, text="Cancel", command=self._cancel).pack(side="right")

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _show_page(self, page: int) -> None:
        self.page = page
        self._clear_content()
        self.back_button.configure(state="normal" if page else "disabled")
        self.next_button.configure(state="normal", text="Next", command=self._next)
        pages: dict[int, Callable[[], None]] = {
            0: self._welcome_page,
            1: self._license_page,
            2: self._destination_page,
            3: self._tasks_page,
            4: self._ready_page,
            5: self._installing_page,
            6: self._finish_page,
        }
        pages[page]()

    def _heading(self, title: str, description: str) -> None:
        ttk.Label(self.content, text=title, font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(self.content, text=description, wraplength=590).pack(anchor="w", pady=(8, 16))

    def _add_reference_image(self, parent: tk.Misc, *, side: bool) -> None:
        image_name = "wizard_side.bmp" if side else "wizard_small.bmp"
        image_path = self.resources / "assets" / "installer" / image_name
        if not image_path.is_file():
            return
        try:
            image = Image.open(image_path)
            if side:
                image.thumbnail((180, 360))
            else:
                image.thumbnail((76, 76))
            self._side_image = ImageTk.PhotoImage(image)
            ttk.Label(parent, image=self._side_image).pack(side="left", padx=(0, 22), fill="y")
        except OSError:
            return

    def _welcome_page(self) -> None:
        layout = ttk.Frame(self.content)
        layout.pack(fill="both", expand=True)
        self._add_reference_image(layout, side=True)
        text = ttk.Frame(layout)
        text.pack(side="left", fill="both", expand=True)
        ttk.Label(text, text=f"Welcome to {APP_NAME}", font=("TkDefaultFont", 18, "bold"), wraplength=370).pack(anchor="w")
        ttk.Label(
            text,
            text=(
                f"Install {APP_NAME} on your computer.\n\n"
                "Fast, offline, and designed for scientific calculations.\n"
                "Includes calculus, equations, matrices, statistics and more.\n\n"
                "To continue, click Next."
            ),
            justify="left",
            wraplength=390,
        ).pack(anchor="w", pady=(20, 0))

    def _license_page(self) -> None:
        self._heading("License Agreement", "You must accept the MIT License before continuing with the installation.")
        licence = self.resources / "payload" / "LICENSE"
        try:
            licence_text = licence.read_text(encoding="utf-8")
        except OSError:
            licence_text = "The bundled MIT License could not be read."
        text = tk.Text(self.content, height=16, wrap="word", padx=8, pady=8)
        text.insert("1.0", licence_text)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        ttk.Checkbutton(self.content, text="I accept the agreement", variable=self.accepted_license).pack(anchor="w", pady=(12, 0))

    def _destination_page(self) -> None:
        self._heading("Select Destination Location", f"Choose the folder where {APP_NAME} will be installed.")
        details = "macOS installs may use /Applications or ~/Applications." if _is_macos() else "Linux installs stay in your home folder and do not require administrator access."
        ttk.Label(self.content, text=details, wraplength=590).pack(anchor="w", pady=(0, 16))
        row = ttk.Frame(self.content)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.install_root).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self._choose_install_root).pack(side="left", padx=(8, 0))
        ttk.Label(
            self.content,
            text=f"The application will be installed as {_app_name_for_platform()} inside the selected folder.",
            wraplength=590,
        ).pack(anchor="w", pady=(16, 0))

    def _choose_install_root(self) -> None:
        current = Path(self.install_root.get()).expanduser()
        initial = current if current.is_dir() else current.parent
        selected = filedialog.askdirectory(title="Choose installation folder", initialdir=str(initial))
        if selected:
            self.install_root.set(selected)

    def _tasks_page(self) -> None:
        self._heading("Select Additional Tasks", "Choose which additional tasks should be performed during installation.")
        shortcut = "Create a Desktop alias" if _is_macos() else "Create a desktop shortcut"
        ttk.Checkbutton(self.content, text=shortcut, variable=self.create_shortcut).pack(anchor="w", pady=(10, 0))

    def _ready_page(self) -> None:
        try:
            target = _safe_install_target(Path(self.install_root.get()))
            target_text = str(target)
        except (OSError, ValueError):
            target_text = self.install_root.get()
        self._heading("Ready to Install", f"Setup is ready to begin installing {APP_NAME} on your computer.")
        summary = ttk.LabelFrame(self.content, text="Installation summary", padding=12)
        summary.pack(fill="both", expand=True)
        shortcut = "Create a Desktop alias" if _is_macos() else "Create a desktop shortcut"
        task = shortcut if self.create_shortcut.get() else "No desktop shortcut"
        ttk.Label(summary, text=f"Destination location:\n{target_text}\n\nAdditional tasks:\n{task}", justify="left", wraplength=540).pack(anchor="nw")
        self.next_button.configure(text="Install")

    def _installing_page(self) -> None:
        self._heading("Installing", f"Please wait while Setup installs {APP_NAME} on your computer.")
        self.status = tk.StringVar(value="Preparing installation…")
        ttk.Label(self.content, textvariable=self.status).pack(anchor="w", pady=(14, 8))
        self.progress = ttk.Progressbar(self.content, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.back_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        threading.Thread(target=self._perform_install, daemon=True).start()

    def _finish_page(self) -> None:
        layout = ttk.Frame(self.content)
        layout.pack(fill="both", expand=True)
        self._add_reference_image(layout, side=True)
        text = ttk.Frame(layout)
        text.pack(side="left", fill="both", expand=True)
        ttk.Label(text, text=f"Completing the {APP_NAME} Setup Wizard", font=("TkDefaultFont", 16, "bold"), wraplength=380).pack(anchor="w")
        ttk.Label(
            text,
            text=f"Setup has finished installing {APP_NAME} on your computer.\n\nClick Finish to exit Setup.",
            justify="left",
            wraplength=390,
        ).pack(anchor="w", pady=(18, 0))
        ttk.Checkbutton(text, text=f"Launch {APP_NAME}", variable=self.launch_after_install).pack(anchor="w", pady=(18, 0))
        self.back_button.configure(state="disabled")
        self.next_button.configure(text="Finish", state="normal")

    def _next(self) -> None:
        if self.page == 1 and not self.accepted_license.get():
            messagebox.showwarning("License Agreement", "Accept the license agreement to continue.", parent=self.root)
            return
        if self.page == 2:
            try:
                _safe_install_target(Path(self.install_root.get()))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Destination Location", str(exc), parent=self.root)
                return
        if self.page == 4:
            self._show_page(5)
            return
        if self.page == 6:
            if self.launch_after_install.get():
                self._launch_application()
            self.root.destroy()
            return
        self._show_page(self.page + 1)

    def _back(self) -> None:
        if self.page > 0:
            self._show_page(self.page - 1)

    def _cancel(self) -> None:
        if self.page == 5:
            messagebox.showinfo("Installing", "Installation is already in progress and cannot be cancelled safely.", parent=self.root)
            return
        self.root.destroy()

    def _set_progress(self, value: int, message: str) -> None:
        self.root.after(0, lambda: (self.progress.configure(value=value), self.status.set(message)))

    def _perform_install(self) -> None:
        try:
            target = _safe_install_target(Path(self.install_root.get()))
            payload_app = self.resources / "payload" / _app_name_for_platform()
            if not payload_app.exists():
                raise FileNotFoundError(f"Bundled application is missing: {payload_app.name}")
            self._set_progress(10, "Preparing the destination…")
            if _is_macos() and target.parent == Path("/Applications"):
                self._install_macos_with_authorization(payload_app, target)
            else:
                self._copy_payload(payload_app, target)
                if _is_macos():
                    self._copy_macos_uninstaller(target.parent)
            self._set_progress(80, "Creating application shortcuts…")
            self._create_shortcuts(target)
            self._set_progress(100, "Installation complete.")
            self.root.after(0, lambda: self._show_page(6))
        except Exception as error:  # The UI must turn a packaging failure into a readable error.
            self.root.after(0, lambda error=error: self._installation_failed(error))

    def _copy_payload(self, payload_app: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        self._set_progress(35, "Copying application files…")
        shutil.copytree(payload_app, target, symlinks=True)
        if not _is_macos():
            executable = target / "ScientificCalculator"
            executable.chmod(executable.stat().st_mode | 0o111)

    def _copy_macos_uninstaller(self, destination: Path) -> None:
        uninstaller = destination / UNINSTALLER_NAME
        if uninstaller.exists():
            shutil.rmtree(uninstaller)
        executable = uninstaller / "Contents" / "MacOS" / "ScientificCalculatorUninstaller"
        executable.parent.mkdir(parents=True, exist_ok=True)
        template = self.resources / "payload" / "uninstall.sh"
        shutil.copy2(template, executable)
        executable.chmod(executable.stat().st_mode | 0o111)
        (uninstaller / "Contents" / "Info.plist").write_text(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\"><dict>"
            "<key>CFBundleDisplayName</key><string>Scientific Calculator Uninstaller</string>"
            "<key>CFBundleExecutable</key><string>ScientificCalculatorUninstaller</string>"
            "<key>CFBundleIdentifier</key><string>io.github.workaybarsh.scientificcalculator.uninstaller</string>"
            "<key>CFBundleName</key><string>Scientific Calculator Uninstaller</string>"
            "<key>CFBundlePackageType</key><string>APPL</string>"
            "</dict></plist>\n",
            encoding="utf-8",
        )

    def _install_macos_with_authorization(self, payload_app: Path, target: Path) -> None:
        stage = Path(tempfile.mkdtemp(prefix="scientific-calculator-setup-", dir="/tmp"))
        try:
            staged_app = stage / APP_BUNDLE_NAME
            shutil.copytree(payload_app, staged_app, symlinks=True)
            self._copy_macos_uninstaller(stage)
            for directory in (stage, staged_app, stage / UNINSTALLER_NAME):
                directory.chmod(0o755)
            destination = target.parent
            commands = [
                "set -eu",
                f"rm -rf -- {shlex.quote(str(target))}",
                f"rm -rf -- {shlex.quote(str(destination / UNINSTALLER_NAME))}",
                f"cp -R {shlex.quote(str(staged_app))} {shlex.quote(str(target))}",
                f"cp -R {shlex.quote(str(stage / UNINSTALLER_NAME))} {shlex.quote(str(destination / UNINSTALLER_NAME))}",
            ]
            installer_script = stage / "install.sh"
            installer_script.write_text("\n".join(commands) + "\n", encoding="utf-8")
            installer_script.chmod(0o755)
            command = "/bin/sh " + shlex.quote(str(installer_script))
            self._set_progress(35, "Requesting permission to copy into Applications…")
            subprocess.run(["osascript", "-e", f"do shell script {json.dumps(command)} with administrator privileges"], check=True)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def _create_shortcuts(self, target: Path) -> None:
        if _is_macos():
            if self.create_shortcut.get():
                desktop = Path.home() / "Desktop"
                desktop.mkdir(parents=True, exist_ok=True)
                shortcut = desktop / APP_BUNDLE_NAME
                if shortcut.is_symlink() or shortcut.exists():
                    if shortcut.is_symlink() or shortcut.is_file():
                        shortcut.unlink()
                    else:
                        raise FileExistsError(f"Refusing to replace an existing Desktop folder: {shortcut}")
                shortcut.symlink_to(target)
            return
        app_menu = Path.home() / ".local" / "share" / "applications"
        app_menu.mkdir(parents=True, exist_ok=True)
        self._write_linux_desktop_file(app_menu / "scientific-calculator.desktop", target, APP_NAME, target / "ScientificCalculator")
        self._write_linux_uninstaller(target, app_menu)
        if self.create_shortcut.get():
            desktop = Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            shortcut = desktop / "scientific-calculator.desktop"
            self._write_linux_desktop_file(shortcut, target, APP_NAME, target / "ScientificCalculator")
            shortcut.chmod(shortcut.stat().st_mode | 0o111)

    @staticmethod
    def _desktop_value(path: Path) -> str:
        return str(path).replace("\\", "\\\\").replace(" ", "\\ ")

    def _write_linux_desktop_file(self, path: Path, target: Path, title: str, executable: Path) -> None:
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={title}\n"
            "Comment=Offline scientific calculator\n"
            f"Exec={self._desktop_value(executable)}\n"
            f"Path={self._desktop_value(target)}\n"
            f"Icon={self._desktop_value(target / 'icons' / 'scientific-calculator.png')}\n"
            "Terminal=false\n"
            "Categories=Education;Science;Math;\n",
            encoding="utf-8",
        )

    def _write_linux_uninstaller(self, target: Path, app_menu: Path) -> None:
        uninstaller = target / "UninstallScientificCalculator"
        target_shell = shlex.quote(str(target))
        menu_shell = shlex.quote(str(app_menu))
        uninstaller.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"target={target_shell}\n"
            f"app_menu={menu_shell}\n"
            "case \"$target\" in \"$HOME\"/*) ;; *) exit 1 ;; esac\n"
            "if command -v zenity >/dev/null 2>&1; then\n"
            "  zenity --question --title='Scientific Calculator Uninstaller' --text='Remove Scientific Calculator and its app launcher?' || exit 0\n"
            "fi\n"
            "pkill -x ScientificCalculator 2>/dev/null || true\n"
            "rm -rf -- \"$target\"\n"
            "rm -f -- \"$app_menu/scientific-calculator.desktop\" \"$app_menu/scientific-calculator-uninstaller.desktop\"\n",
            encoding="utf-8",
        )
        uninstaller.chmod(uninstaller.stat().st_mode | 0o111)
        self._write_linux_desktop_file(
            app_menu / "scientific-calculator-uninstaller.desktop",
            target,
            f"{APP_NAME} Uninstaller",
            uninstaller,
        )

    def _installation_failed(self, error: Exception) -> None:
        self.back_button.configure(state="normal")
        self.next_button.configure(state="normal", text="Back")
        self.next_button.configure(command=self._back)
        messagebox.showerror("Installation failed", str(error), parent=self.root)

    def _launch_application(self) -> None:
        try:
            target = _safe_install_target(Path(self.install_root.get()))
            if _is_macos():
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen([str(target / "ScientificCalculator")])
        except (OSError, ValueError) as error:
            messagebox.showwarning("Launch Scientific Calculator", str(error), parent=self.root)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()
