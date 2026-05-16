"""Semi-automatic wizard: deploy Set Play relay worker (Node, npm, wrangler login/deploy)."""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services.set_play_worker_paths import (
    resolve_set_play_deploy_directory,
    sync_worker_template_to_deploy,
    worker_template_bundle_path,
)

# HTTPS workers.dev URL in wrangler deploy output
_WORKERS_DEV_RE = re.compile(r"https://[a-zA-Z0-9][-a-zA-Z0-9.]*\.workers\.dev")


def https_to_wss_worker_url(https_url: str) -> str:
    u = https_url.strip().rstrip("/")
    if u.startswith("https://"):
        return "wss://" + u[8:]
    if u.startswith("http://"):
        return "ws://" + u[7:]
    return u


class SetPlayRelayDeployWizard(QDialog):
    """Overview → extract → Node → npm install → wrangler login → deploy."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        on_deploy_url: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create your own Set Play relay")
        self.resize(560, 420)
        self._on_deploy_url = on_deploy_url
        self._deploy_dir = resolve_set_play_deploy_directory()
        self._bundle = worker_template_bundle_path()
        self._process: QProcess | None = None
        self._last_https_url: str = ""

        root = QVBoxLayout(self)
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # ---- Page 0: overview
        overview = QWidget()
        ov_l = QVBoxLayout(overview)
        intro = QLabel(
            "This assistant will:\n\n"
            "• Copy the relay worker template to a folder on your computer\n"
            "• Check for Node.js (and on Windows you can try installing Node LTS with winget)\n"
            "• Run npm install (includes Wrangler)\n"
            "• Open a browser so you can sign in to Cloudflare (wrangler login)\n"
            "• Deploy the worker to your Cloudflare account (wrangler deploy)\n\n"
            "You will need a Cloudflare account. The browser step cannot be skipped."
        )
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ov_l.addWidget(intro)
        self._path_lbl = QLabel()
        self._path_lbl.setWordWrap(True)
        self._path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._refresh_path_label()
        ov_l.addWidget(self._path_lbl)
        ov_l.addStretch()
        self._stack.addWidget(overview)

        # ---- Step 1 (Node) — custom row with winget
        node_w = QWidget()
        node_l = QVBoxLayout(node_w)
        node_l.addWidget(QLabel("<b>Step 1 — Node.js</b>"))
        node_l.addWidget(
            QLabel(
                "Verify node and npm, or on Windows install Node LTS with winget (may prompt UAC). "
                "After installing, restart this app or use a new terminal."
            )
        )
        self._log_node = QTextEdit()
        self._log_node.setReadOnly(True)
        node_l.addWidget(self._log_node, 1)
        node_btn_row = QHBoxLayout()
        run_node = QPushButton("Run this step")
        run_node.clicked.connect(lambda: self._run_current_step(self._log_node))
        node_btn_row.addWidget(run_node)
        self._winget_btn = QPushButton("Install Node LTS (winget)")
        self._winget_btn.setVisible(sys.platform == "win32")
        self._winget_btn.clicked.connect(lambda: self._install_node_winget(self._log_node))
        node_btn_row.addWidget(self._winget_btn)
        node_btn_row.addStretch()
        node_l.addLayout(node_btn_row)
        self._stack.addWidget(node_w)
        self._log_npm = self._make_step_page(
            "Step 2 — Dependencies",
            "Runs npm install in the deploy folder (installs Wrangler for this project).",
        )
        self._log_login = self._make_step_page(
            "Step 3 — Cloudflare login",
            "Runs wrangler login. Complete sign-in in the browser; this window will continue when finished.",
        )
        self._log_deploy = self._make_step_page(
            "Step 4 — Deploy",
            "Runs wrangler deploy. When it succeeds, click Next to finish and copy your URL.",
        )
        self._done_page = QWidget()
        done_l = QVBoxLayout(self._done_page)
        done_l.addWidget(
            QLabel(
                "Copy the relay URL (wss) into Set Playback, or use Add to Set Playback."
            )
        )
        self._url_out = QTextEdit()
        self._url_out.setReadOnly(True)
        self._url_out.setMaximumHeight(72)
        done_l.addWidget(self._url_out)
        done_btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy relay URL")
        copy_btn.clicked.connect(self._copy_url)
        add_btn = QPushButton("Add to Set Playback…")
        add_btn.clicked.connect(self._add_to_set_playback)
        done_btn_row.addWidget(copy_btn)
        done_btn_row.addWidget(add_btn)
        done_btn_row.addStretch()
        done_l.addLayout(done_btn_row)
        self._stack.addWidget(self._done_page)

        bbox = QDialogButtonBox()
        self._btn_back = QPushButton("Back")
        self._btn_next = QPushButton("Confirm")
        self._btn_cancel = QPushButton("Cancel")
        bbox.addButton(self._btn_back, QDialogButtonBox.ButtonRole.ActionRole)
        bbox.addButton(self._btn_next, QDialogButtonBox.ButtonRole.ActionRole)
        bbox.addButton(self._btn_cancel, QDialogButtonBox.ButtonRole.RejectRole)
        self._btn_back.clicked.connect(self._go_back)
        self._btn_next.clicked.connect(self._go_forward)
        self._btn_cancel.clicked.connect(self.reject)
        root.addWidget(bbox)

        self._page_idx = 0
        self._sync_done = False
        self._update_nav()

    def _refresh_path_label(self) -> None:
        self._path_lbl.setText(
            f"<b>Deploy folder</b> (all commands run here):<br><code>{self._deploy_dir}</code>"
        )

    def _make_step_page(self, title: str, desc: str) -> QTextEdit:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        d = QLabel(desc)
        d.setWordWrap(True)
        lay.addWidget(d)
        log = QTextEdit()
        log.setReadOnly(True)
        lay.addWidget(log, 1)
        run_row = QHBoxLayout()
        run_btn = QPushButton("Run this step")
        run_btn.clicked.connect(lambda checked=False, lg=log: self._run_current_step(lg))
        run_row.addWidget(run_btn)
        run_row.addStretch()
        lay.addLayout(run_row)
        self._stack.addWidget(w)
        return log

    def _update_nav(self) -> None:
        n = self._stack.count()
        self._btn_back.setEnabled(self._page_idx > 0)
        self._btn_next.setVisible(self._page_idx < n - 1)
        if self._page_idx == 0:
            self._btn_next.setText("Confirm")
        elif self._page_idx < n - 1:
            self._btn_next.setText("Next")

    def _go_back(self) -> None:
        if self._page_idx > 0:
            self._page_idx -= 1
            self._stack.setCurrentIndex(self._page_idx)
            self._update_nav()

    def _go_forward(self) -> None:
        n = self._stack.count()
        if self._page_idx == 0:
            if not self._bundle or not self._bundle.is_dir():
                QMessageBox.warning(
                    self,
                    "Missing worker template",
                    "The relay worker template was not found in the application bundle. "
                    "Use a full install or run from source.",
                )
                return
            try:
                sync_worker_template_to_deploy(self._bundle, self._deploy_dir, log_line=None)
            except OSError as e:
                QMessageBox.warning(
                    self,
                    "Extract failed",
                    f"Could not copy worker files:\n{e}",
                )
                return
            self._sync_done = True
            self._page_idx = 1
            self._stack.setCurrentIndex(self._page_idx)
            self._update_nav()
            return

        if self._page_idx < n - 2:
            self._page_idx += 1
            self._stack.setCurrentIndex(self._page_idx)
            self._update_nav()
        elif self._page_idx == n - 2:
            self._page_idx = n - 1
            self._stack.setCurrentIndex(self._page_idx)
            self._update_nav()

    def _run_current_step(self, log: QTextEdit) -> None:
        if not self._sync_done:
            self._append_log(log, "Use Confirm on the first screen to extract the worker.")
            return
        deploy = self._deploy_dir
        if self._page_idx == 1:
            self._run_node_check(log)
            return
        if self._page_idx == 2:
            self._run_npm_install(log, deploy)
            return
        if self._page_idx == 3:
            self._run_wrangler_login(log, deploy)
            return
        if self._page_idx == 4:
            self._run_wrangler_deploy(log, deploy)

    def _append_log(self, log: QTextEdit, text: str) -> None:
        log.append(text.rstrip())
        sb = log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _run_cmd(
        self,
        log: QTextEdit,
        program: str,
        args: list[str],
        *,
        cwd: Path | None = None,
    ) -> None:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._append_log(log, "(A command is already running in this dialog.)")
            return
        proc = QProcess(self)
        self._process = proc
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if cwd is not None:
            proc.setWorkingDirectory(str(cwd))
        proc.setProcessEnvironment(QProcessEnvironment.systemEnvironment())

        def read_out() -> None:
            data = bytes(proc.readAllStandardOutput()).decode(errors="replace")
            if data:
                self._append_log(log, data)

        proc.readyReadStandardOutput.connect(read_out)

        def finished(code: int, status: QProcess.ExitStatus) -> None:
            read_out()
            self._append_log(log, f"-- exit code {code} --")
            if self._page_idx == 4 and code == 0:
                text = log.toPlainText()
                m = _WORKERS_DEV_RE.search(text)
                if m:
                    self._last_https_url = m.group(0).rstrip("/")
                    wss = https_to_wss_worker_url(self._last_https_url)
                    self._url_out.setPlainText(wss)
                    if self._on_deploy_url:
                        self._on_deploy_url(wss)
            self._process = None

        proc.finished.connect(finished)
        self._append_log(log, f"$ {program} {' '.join(args)}")
        proc.start(program, args)

    def _run_node_check(self, log: QTextEdit) -> None:
        if sys.platform == "win32":
            self._run_cmd(log, "cmd.exe", ["/c", "where node && node -v && npm -v"])
        else:
            self._run_cmd(log, "sh", ["-lc", "command -v node && node -v && npm -v"])

    def _install_node_winget(self, log: QTextEdit) -> None:
        if sys.platform != "win32":
            return
        self._run_cmd(
            log,
            "winget.exe",
            [
                "install",
                "OpenJS.NodeJS.LTS",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
        )

    def _run_npm_install(self, log: QTextEdit, deploy: Path) -> None:
        if sys.platform == "win32":
            cmd = f'cd /d "{deploy}" && npm install'
            self._run_cmd(log, "cmd.exe", ["/c", cmd])
        else:
            self._run_cmd(log, "npm", ["install"], cwd=deploy)

    def _run_wrangler_login(self, log: QTextEdit, deploy: Path) -> None:
        if sys.platform == "win32":
            cmd = f'cd /d "{deploy}" && npx wrangler login'
            self._run_cmd(log, "cmd.exe", ["/c", cmd])
        else:
            self._run_cmd(log, "npx", ["wrangler", "login"], cwd=deploy)

    def _run_wrangler_deploy(self, log: QTextEdit, deploy: Path) -> None:
        if sys.platform == "win32":
            cmd = f'cd /d "{deploy}" && npx wrangler deploy'
            self._run_cmd(log, "cmd.exe", ["/c", cmd])
        else:
            self._run_cmd(log, "npx", ["wrangler", "deploy"], cwd=deploy)

    def _copy_url(self) -> None:
        t = self._url_out.toPlainText().strip()
        if t:
            QApplication.clipboard().setText(t)

    def _add_to_set_playback(self) -> None:
        url = self._url_out.toPlainText().strip()
        if not url:
            QMessageBox.warning(self, "Set Playback", "Deploy first to get a URL.")
            return
        name, ok = QInputDialog.getText(
            self,
            "Relay name",
            "Name for this relay (e.g. your band name):",
        )
        if not ok or not name.strip():
            return
        from ..services.preferences import get_set_play_relays, set_set_play_relays

        relays = list(get_set_play_relays())
        relays.append(
            {
                "id": str(uuid.uuid4()),
                "name": name.strip(),
                "url": url.strip().rstrip("/"),
            }
        )
        set_set_play_relays(relays)
        p = self.parent()
        if p is not None and hasattr(p, "_refresh_set_playback_table"):
            p._refresh_set_playback_table()
        QMessageBox.information(self, "Set Playback", "Relay added.")
        self.accept()
