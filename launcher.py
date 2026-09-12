from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from game.net.client_app import run_client
    from game.net.server import GameHost
    from game.ui import FONT_PANEL, FONT_SUBTITLE, FONT_TITLE, FONT_UI_BOLD, PALETTE, _configure_windows_dpi_awareness, run_app
else:
    from .net.client_app import run_client
    from .net.server import GameHost
    from .ui import FONT_PANEL, FONT_SUBTITLE, FONT_TITLE, FONT_UI_BOLD, PALETTE, _configure_windows_dpi_awareness, run_app


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        _configure_windows_dpi_awareness()
        super().__init__()
        self.title("山中小屋")
        self.geometry("820x780")
        self.minsize(700, 760)
        self.configure(bg=PALETTE["bg"])
        self._build()

    def _build(self) -> None:
        panel = tk.Frame(
            self,
            bg=PALETTE["panel"],
            padx=34,
            pady=30,
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        # 使用明确的最小内容区，启动器首次布局时按钮尺寸稳定，说明文字也不会被裁掉。
        panel.place(relx=0.5, rely=0.5, anchor="center", width=680, height=700)

        tk.Label(
            panel,
            text="山中小屋",
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=FONT_TITLE,
        ).pack(pady=(0, 8))
        tk.Label(
            panel,
            text="选择要启动的模式",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=FONT_SUBTITLE,
        ).pack(pady=(0, 22))

        self.btn_local_mode = self._mode_button(panel, "本地模式", "单人或同屏热座，支持机器人。", self._launch_local)
        self.btn_client_mode = self._mode_button(panel, "联机模式", "连接主机或远程隧道，进入联机大厅。", self._launch_client)
        self.btn_host_mode = self._mode_button(panel, "启动联机主机", "房主电脑先启动主机，再让客户端连接。", self._launch_host)
        self.btn_local_mode.pack(fill="x", pady=5)
        self.btn_client_mode.pack(fill="x", pady=5)
        self.btn_host_mode.pack(fill="x", pady=5)

        tk.Label(
            panel,
            text="远程联机时：房主先启动主机和 NATFRP TCP 隧道，其他玩家在联机模式里填写隧道地址和远程端口。",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=FONT_PANEL,
            justify="left",
            wraplength=560,
        ).pack(fill="x", pady=(18, 0))

    def _mode_button(self, parent, title: str, detail: str, command):
        frame = tk.Frame(parent, bg=PALETTE["panel2"], highlightthickness=1, highlightbackground=PALETTE["outline"])
        label = tk.Label(frame, text=title, bg=PALETTE["panel2"], fg=PALETTE["text"], font=FONT_UI_BOLD, anchor="w", padx=14, pady=8)
        label.pack(fill="x")
        sub = tk.Label(frame, text=detail, bg=PALETTE["panel2"], fg=PALETTE["muted"], font=FONT_PANEL, anchor="w", padx=14, pady=0)
        sub.pack(fill="x", pady=(0, 10))
        for widget in (frame, label, sub):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", lambda _e, f=frame: f.config(bg=PALETTE["panel3"]))
            widget.bind("<Leave>", lambda _e, f=frame: f.config(bg=PALETTE["panel2"]))
        return frame

    def _launch_local(self) -> None:
        self.destroy()
        run_app()

    def _launch_client(self) -> None:
        self.destroy()
        run_client()

    def _launch_host(self) -> None:
        self.destroy()
        HostControlApp().mainloop()


class HostControlApp(tk.Tk):
    def __init__(self) -> None:
        _configure_windows_dpi_awareness()
        super().__init__()
        self.title("山中小屋 - 联机主机")
        self.geometry("720x520")
        self.minsize(640, 460)
        self.configure(bg=PALETTE["bg"])
        self.host: GameHost | None = None
        self.host_thread: threading.Thread | None = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        panel = tk.Frame(self, bg=PALETTE["panel"], padx=26, pady=22, highlightthickness=1, highlightbackground=PALETTE["outline"])
        panel.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(panel, text="联机主机", bg=PALETTE["panel"], fg=PALETTE["accent"], font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        tk.Label(panel, text="启动后客户端连接本机 IP:端口；远程联机请配合 NATFRP TCP 隧道。", bg=PALETTE["panel"], fg=PALETTE["muted"], font=FONT_PANEL).pack(anchor="w", pady=(2, 14))

        form = tk.Frame(panel, bg=PALETTE["panel"])
        form.pack(fill="x", pady=(0, 10))
        form.grid_columnconfigure(1, weight=1)
        tk.Label(form, text="端口", bg=PALETTE["panel"], fg=PALETTE["text"], font=FONT_PANEL, width=8, anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry_port = tk.Entry(form, bg="#181c22", fg=PALETTE["text"], insertbackground=PALETTE["text"], relief="flat")
        self.entry_port.insert(0, "8765")
        self.entry_port.grid(row=0, column=1, sticky="ew", pady=4)

        tk.Label(form, text="口令", bg=PALETTE["panel"], fg=PALETTE["text"], font=FONT_PANEL, width=8, anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry_password = tk.Entry(form, bg="#181c22", fg=PALETTE["text"], insertbackground=PALETTE["text"], relief="flat")
        self.entry_password.grid(row=1, column=1, sticky="ew", pady=4)

        buttons = tk.Frame(panel, bg=PALETTE["panel"])
        buttons.pack(fill="x", pady=(2, 10))
        self.btn_start_host = tk.Button(buttons, text="启动主机", command=self._start_host, bg=PALETTE["accent"], fg="#111", relief="flat", font=FONT_UI_BOLD, padx=22, pady=8, cursor="hand2")
        self.btn_start_host.pack(side="left")
        self.btn_stop_host = tk.Button(buttons, text="停止主机", command=self._stop_host, bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD, padx=22, pady=8, cursor="hand2", state="disabled")
        self.btn_stop_host.pack(side="left", padx=(8, 0))
        self.btn_open_client = tk.Button(buttons, text="打开本机客户端", command=self._open_client_window, bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD, padx=22, pady=8, cursor="hand2")
        self.btn_open_client.pack(side="right")

        self.log_text = tk.Text(panel, height=13, bg="#11151a", fg=PALETTE["text"], insertbackground=PALETTE["text"], relief="flat", font=FONT_PANEL, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.config(state="disabled")
        self._append_log("主机尚未启动。")

    def _append_log(self, message: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def _start_host(self) -> None:
        if self.host is not None:
            return
        try:
            port = int(self.entry_port.get().strip() or "8765")
        except ValueError:
            self._append_log("端口必须是数字。")
            return
        password = self.entry_password.get()
        host = GameHost(port=port, password=password)
        original_log = host._log_network_locked

        def gui_log(message: str) -> None:
            original_log(message)
            try:
                self.after(0, self._append_log, message)
            except Exception:
                pass

        host._log_network_locked = gui_log  # type: ignore[method-assign]
        try:
            host.start()
        except OSError as exc:
            self._append_log(f"启动失败：{exc}")
            return
        self.host = host
        self.host_thread = threading.Thread(target=self._run_host_loop, daemon=True)
        self.host_thread.start()
        self.btn_start_host.config(state="disabled")
        self.btn_stop_host.config(state="normal")
        self._append_log(f"主机已启动：127.0.0.1:{port}")
        self._append_log("本机测试可打开客户端并填写 127.0.0.1 和此端口。")
        self._append_log("远程测试请在 NATFRP 创建 TCP 隧道，本地端口填此端口。")

    def _run_host_loop(self) -> None:
        try:
            if self.host is not None:
                self.host.run_loop()
        except Exception as exc:
            try:
                self.after(0, self._append_log, f"主机异常：{exc}")
            except Exception:
                pass

    def _stop_host(self) -> None:
        if self.host is not None:
            self.host.stop()
            self.host = None
        self.btn_start_host.config(state="normal")
        self.btn_stop_host.config(state="disabled")
        self._append_log("主机已停止。")

    def _open_client_window(self) -> None:
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--mode", "client"]
        else:
            command = [sys.executable, str(Path(__file__).resolve()), "--mode", "client"]
        try:
            subprocess.Popen(command)
            self._append_log("已打开一个本机客户端窗口。")
        except OSError as exc:
            self._append_log(f"打开客户端失败：{exc}")

    def _close(self) -> None:
        self._stop_host()
        self.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="《山中小屋》统一启动器")
    parser.add_argument("--mode", choices=("launcher", "local", "client", "host"), default="launcher")
    args = parser.parse_args()
    if args.mode == "local":
        run_app()
    elif args.mode == "client":
        run_client()
    elif args.mode == "host":
        HostControlApp().mainloop()
    else:
        LauncherApp().mainloop()


if __name__ == "__main__":
    main()
