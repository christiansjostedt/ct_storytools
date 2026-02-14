# gui_utils/window_main.py
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QTreeView, QPlainTextEdit, QSplitter, QVBoxLayout, QHBoxLayout,
    QWidget, QToolBar, QLabel, QComboBox, QPushButton, QListWidget, QScrollArea,
    QMessageBox, QCheckBox
)
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import Qt, QSettings, QTimer, QItemSelectionModel

from gui_utils.styles import apply_dark_theme, TREE_STYLE, EDITOR_STYLE, LIST_STYLE, GROUPBOX_STYLE
from gui_utils.constants import JOBTYPE_LIST

from gui_utils.config_manager import ConfigManager
from gui_utils.selection_state import SelectionState
from gui_utils.executor import Executor

from gui_utils.tree_helpers import populate_tree, auto_resize_tree

from gui_utils.window_actions import (
    open_config,
    refresh_config,
    save_changes,
    create_new_sequence,
    create_new_shot,
    show_context_menu,
    view_globals
)

from gui_utils.window_events import connect_events, on_tree_selection_changed, on_tree_current_changed

from gui_utils.editor_highlighter import ShotEditorHighlighter

from gui_utils.run_manager import RunManager


class StorytoolsWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("ct_storytools – PySide6 Edition")
        self.resize(1600, 1000)

        self.config_manager = ConfigManager()
        self.selection = SelectionState()
        self.executor = Executor(self.statusBar())

        self.run_manager = RunManager(self)

        self.setAcceptDrops(True)
        self._setup_ui()

        connect_events(self)

        self.tree.customContextMenuRequested.connect(lambda pos: show_context_menu(self, pos))

        self._restore_window_state()

        self.last_selected_shot = None

        QTimer.singleShot(100, self._init_hosts_pane)

    def _init_hosts_pane(self):
        globals_data = self.config_manager.config.get("globals", {})
        jobtype = self.selection.selected_jobtype
        self.selection.update_host_checkboxes(self.hosts_layout, globals_data, jobtype)
        if self.hosts_layout.count() == 0:
            self.hosts_layout.addWidget(QLabel("Select jobtype to view hosts"))
            self.hosts_layout.addStretch()

    def _setup_ui(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_open = QAction("Open Config", self)
        act_open.triggered.connect(lambda: open_config(self))
        toolbar.addAction(act_open)

        act_refresh = QAction("Refresh", self)
        act_refresh.triggered.connect(lambda: refresh_config(self))
        toolbar.addAction(act_refresh)

        act_globals = QAction("View Globals", self)
        act_globals.triggered.connect(lambda: view_globals(self))
        toolbar.addAction(act_globals)

        toolbar.addSeparator()

        self.act_save = QAction("Save", self)
        self.act_save.triggered.connect(lambda: save_changes(self))
        self.act_save.setEnabled(False)
        toolbar.addAction(self.act_save)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        self.setCentralWidget(main_splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        top_left_row = QHBoxLayout()
        seq_lbl = QLabel("Sequences & Shots")
        seq_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #d0d0d0;")
        top_left_row.addWidget(seq_lbl)
        self.project_lbl = QLabel("Project: None")
        self.project_lbl.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        top_left_row.addStretch()
        top_left_row.addWidget(self.project_lbl)
        left_layout.addLayout(top_left_row)

        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        self.tree.setSelectionBehavior(QTreeView.SelectRows)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setStyleSheet(TREE_STYLE)
        left_layout.addWidget(self.tree, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.btn_new_seq = QPushButton("+ Sequence")
        self.btn_new_seq.setEnabled(False)
        self.btn_new_seq.clicked.connect(lambda: create_new_sequence(self))
        self.btn_new_seq.setStyleSheet("background-color: #2a6b3a; color: white; padding: 6px;")
        btn_layout.addWidget(self.btn_new_seq)

        self.btn_new_shot = QPushButton("+ Shot")
        self.btn_new_shot.setEnabled(False)
        self.btn_new_shot.clicked.connect(lambda: create_new_shot(self))
        self.btn_new_shot.setStyleSheet("background-color: #3a8a4a; color: white; padding: 6px;")
        btn_layout.addWidget(self.btn_new_shot)

        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        main_splitter.addWidget(left_widget)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(8, 8, 8, 8)

        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.setObjectName("rightSplitter")

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)

        editor_top = QHBoxLayout()
        self.editor_label = QLabel("Shot Editor – no shot selected")
        self.editor_label.setStyleSheet("font-weight: bold; color: #d0d0d0;")
        editor_top.addWidget(self.editor_label)

        font_layout = QHBoxLayout()
        font_lbl = QLabel("Font size:")
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Small", "Medium", "Large"])
        self.font_combo.setCurrentText("Medium")
        font_layout.addWidget(font_lbl)
        font_layout.addWidget(self.font_combo)
        editor_top.addStretch()
        editor_top.addLayout(font_layout)

        editor_layout.addLayout(editor_top)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setStyleSheet(EDITOR_STYLE)
        self.editor.setFont(QFont("Consolas", 12))
        editor_layout.addWidget(self.editor, 1)

        self.highlighter = ShotEditorHighlighter(self.editor.document())

        right_splitter.addWidget(editor_widget)

        hosts_queue_splitter = QSplitter(Qt.Orientation.Vertical)
        hosts_queue_splitter.setObjectName("hostsQueueSplitter")

        hosts_widget = QWidget()
        hosts_layout_outer = QVBoxLayout(hosts_widget)
        hosts_layout_outer.setContentsMargins(0, 0, 0, 0)
        hosts_title = QLabel("Hosts")
        hosts_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #d0d0d0; background-color: #2a2a2a; padding: 8px;")
        hosts_layout_outer.addWidget(hosts_title)

        scroll_hosts = QScrollArea()
        scroll_hosts.setWidgetResizable(True)
        hosts_scroll_widget = QWidget()
        self.hosts_layout = QVBoxLayout(hosts_scroll_widget)
        self.hosts_layout.setContentsMargins(8, 8, 8, 8)
        self.hosts_layout.setSpacing(4)
        scroll_hosts.setWidget(hosts_scroll_widget)
        hosts_layout_outer.addWidget(scroll_hosts)

        hosts_queue_splitter.addWidget(hosts_widget)

        queue_widget = QWidget()
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_title = QLabel("Queue (pending jobs)")
        queue_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #d0d0d0; background-color: #2a2a2a; padding: 8px;")
        queue_layout.addWidget(queue_title)

        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet(LIST_STYLE)
        queue_layout.addWidget(self.queue_list)

        hosts_queue_splitter.addWidget(queue_widget)
        hosts_queue_splitter.setSizes([300, 200])

        right_splitter.addWidget(hosts_queue_splitter)
        right_layout.addWidget(right_splitter)
        right_splitter.setSizes([800, 400])
        right_splitter.setCollapsible(1, False)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self.jobtype_combo = QComboBox()
        self.jobtype_combo.setMinimumWidth(180)
        self.jobtype_combo.addItems(JOBTYPE_LIST)
        bottom_row.addWidget(QLabel("Jobtype:"))
        bottom_row.addWidget(self.jobtype_combo)
        bottom_row.addStretch()

        self.btn_run_all = QPushButton("Run All")
        self.btn_run_all.setEnabled(False)
        self.btn_run_all.clicked.connect(self.run_manager.run_all_shots)
        self.btn_run_all.setStyleSheet("background-color: #2e7d32; color: white; min-width: 140px; padding: 8px;")
        bottom_row.addWidget(self.btn_run_all)

        self.btn_run_selected = QPushButton("Run Selected")
        self.btn_run_selected.setEnabled(False)
        self.btn_run_selected.clicked.connect(self.run_manager.run_selected_shots)
        self.btn_run_selected.setStyleSheet("background-color: #f57c00; color: white; min-width: 140px; padding: 8px;")
        bottom_row.addWidget(self.btn_run_selected)

        # Checkbox to keep temp configs (clear visual state)
        self.keep_temp_checkbox = QCheckBox("Keep temp configs after run")
        self.keep_temp_checkbox.setChecked(False)
        bottom_row.addWidget(self.keep_temp_checkbox)

        right_layout.addLayout(bottom_row)

        main_splitter.addWidget(right_container)
        main_splitter.setSizes([300, 1300])

        self.statusBar().showMessage("Ready – open a config file to begin")

    def _restore_window_state(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        main_splitter = self.findChild(QSplitter, "mainSplitter")
        if main_splitter:
            sizes = self.settings.value("main_splitter_sizes")
            if sizes:
                main_splitter.setSizes([int(s) for s in sizes])

        right_splitter = self.findChild(QSplitter, "rightSplitter")
        if right_splitter:
            sizes = self.settings.value("right_splitter_sizes")
            if sizes:
                right_splitter.setSizes([int(s) for s in sizes])
            else:
                right_splitter.setSizes([800, 400])

        hosts_queue_splitter = self.findChild(QSplitter, "hostsQueueSplitter")
        if hosts_queue_splitter:
            sizes = self.settings.value("hosts_queue_splitter_sizes")
            if sizes:
                hosts_queue_splitter.setSizes([int(s) for s in sizes])
            else:
                hosts_queue_splitter.setSizes([300, 200])

    def _save_window_state(self):
        self.settings.setValue("geometry", self.saveGeometry())

        main_splitter = self.findChild(QSplitter, "mainSplitter")
        if main_splitter:
            self.settings.setValue("main_splitter_sizes", main_splitter.sizes())

        right_splitter = self.findChild(QSplitter, "rightSplitter")
        if right_splitter:
            self.settings.setValue("right_splitter_sizes", right_splitter.sizes())

        hosts_queue_splitter = self.findChild(QSplitter, "hostsQueueSplitter")
        if hosts_queue_splitter:
            self.settings.setValue("hosts_queue_splitter_sizes", hosts_queue_splitter.sizes())

    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)

    def _update_editor_font(self, size_text):
        sizes = {"Small": 10, "Medium": 12, "Large": 14}
        self.editor.setFont(QFont("Consolas", sizes.get(size_text, 12)))

    def refresh_tree_only(self):
        populate_tree(
            self.tree,
            self.config_manager.config,
            self.config_manager.project,
            self.config_manager.shot_ranges,
            self.config_manager.original_lines
        )
        auto_resize_tree(self.tree)

        selection_model = self.tree.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(lambda s, d: on_tree_selection_changed(self, s, d))
            selection_model.currentChanged.connect(lambda c, p: on_tree_current_changed(self, c, p))

        if self.last_selected_shot:
            seq, shot = self.last_selected_shot
            model = self.tree.model()
            found = False
            for row in range(model.rowCount()):
                seq_item = model.item(row)
                if seq_item and seq_item.text() == seq:
                    for child_row in range(seq_item.rowCount()):
                        child_item = seq_item.child(child_row)
                        if child_item:
                            data = child_item.data(Qt.ItemDataRole.UserRole)
                            if data and data == (seq, shot):
                                index = model.indexFromItem(child_item)
                                self.tree.setCurrentIndex(index)
                                selection_model.select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                                QTimer.singleShot(0, lambda: on_tree_selection_changed(self, None, None))
                                found = True
                                break
                    if found:
                        break

        QTimer.singleShot(0, self.tree.expandAll)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() == '.txt':
                self.config_manager.config_path = path
                refresh_config(self)
                event.acceptProposedAction()
            else:
                QMessageBox.warning(self, "Invalid File", "Please drop a .txt config file.")
                event.ignore()