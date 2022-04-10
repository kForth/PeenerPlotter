"""
TODO:
# - Peener stow position? (instead of just slow peening)
- Better design selector
- Tune Currents
"""

import os
import glob
import json
from typing import Union

from PyQt5 import uic
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject, QSize
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QProgressDialog, QListView
from PyQt5.QtGui import QIcon

from canvas import PeenerCanvas
from machine import Machine
from util import *

class MainWindow(QMainWindow):
    settings_changed = pyqtSignal(object)

    settings = {
        '_version': 6,
        'port': '/dev/ttyAMA0',
        'tag_diam': 38 * 2,  # mm (engraveable area diameter)
        'line_width': 0.75,  # mm - Peener line width
        'dry_run_only': False,
        'show_travel_lines': True,
        'colorful_paths': False,
        'show_machine_pos': True,
        'draw_border': False,
        'border_margin': 1
    }

    PREMADE_DESIGNS = { "Load Premade Design": None }

    SETTINGS_FP = "_settings.json"

    FULL_SCREEN = True
    HIDE_TITLEBAR = False

    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)
        
        self._background_process_dialog = None
        self._active_process = None
        self._settings_ui = (
            ('dry_run_only', self.actionDry_Run_Only),
            ('show_travel_lines', self.actionShow_Travel_Lines),
            ('colorful_paths', self.actionShow_Colorful_Paths),
            ('draw_border', self.drawBorderButton)
        )

        self.load_settings_from_file()
        self.save_settings_to_file()

        # Init Custom Path Drawing Widget
        self.canvas = PeenerCanvas(self.settings)
        self.canvas_label.parent().layout().replaceWidget(self.canvas_label, self.canvas)
        self.canvas_label.hide()

        # Premade Design Select
        icon_size = 64
        self.designSelectBox.setView(QListView())
        self.designSelectBox.setIconSize(QSize(icon_size, icon_size))
        self.designSelectBox.setStyleSheet(f"QListView::item {{ height:{icon_size}px; }}")
        self.refresh_premade_designs()

        # Init Machine
        self.machine = Machine(self, self.settings)

        # File Menu Actions
        self.action_saveDesign.triggered.connect(self.save_design)
        self.action_loadDesign.triggered.connect(self.load_design)
        self.actionRefresh_Templates.triggered.connect(self.refresh_premade_designs)

        # Canvas Menu Actions
        self.actionLoad_Canvas_Template.triggered.connect(self.load_canvas_template)
        self.actionClear_Canvas_Template.triggered.connect(self.canvas.clear_template)
        self.actionShow_Travel_Lines.toggled.connect(self.update_settings_from_ui)
        self.actionShow_Colorful_Paths.toggled.connect(self.update_settings_from_ui)

        # Machine Actions
        self.actionHome_Machine.triggered.connect(self.on_home_machine)
        self.actionPut_Machine_To_Sleep.triggered.connect(lambda *a, **k: self.machine.connect_and_sleep())
        self.actionWrite_Default_Settings.triggered.connect(lambda *a, **k: self.do_background_process(
            "Writing Machine Defaults",
            "Writing Machine Defaults, Please wait...",
            self.write_machine_defaults
        ))
        self.actionHome_X.triggered.connect(lambda *a, **k: self.do_background_process(
            "Homing X Axis",
            "Homing X Axis, Please wait...",
            self.machine.home_x
        ))
        self.actionHome_Y.triggered.connect(lambda *a, **k: self.do_background_process(
            "Homing Y Axis",
            "Homing Y Axis, Please wait...",
            self.machine.home_y
        ))
        self.actionHome_Clamp.triggered.connect(lambda *a, **k: self.do_background_process(
            "Homing Z Axis",
            "Homing Z Axis, Please wait...",
            self.machine.home_clamp
        ))

        # Clamp Actions
        self.actionOpen_Clamp.triggered.connect(lambda *a, **k: self.do_background_process(
            "Opening Clamp",
            "Opening Clamp, Please wait...",
            self.machine.home_clamp
        ))
        self.actionClose_Clamp.triggered.connect(lambda *a, **k: self.do_background_process(
            "Closing Clamp",
            "Closing Clamp, Please wait...",
            self.machine.close_clamp
        ))

        # Pizza Tray Actions
        self.actionSpin_Tray_360_CCW.triggered.connect(lambda *a, **k: self.do_background_process(
            "Spinning Tray CCW",
            "Spinning Tray CCW, Please wait...",
            self.machine.spin_tray_routine, 1, self.machine.TRAY_CCW
        ))
        self.actionSpin_Tray_360_CW.triggered.connect(lambda *a, **k: self.do_background_process(
            "Spinning Tray CW",
            "Spinning Tray CW, Please wait...",
            self.machine.spin_tray_routine, 1, self.machine.TRAY_CW
        ))
        self.actionDispense_Tag.triggered.connect(lambda *a, **k: self.do_background_process(
            "Dispensing Tag",
            "Dispensing Tag, Please wait...",
            self.machine.dispense_tag_routine
        ))
        # self.actionHome_Tray.triggered.connect(self.machine.home_tray)

        # Peener Motor Actions
        self.actionPulse_Peener_Once.triggered.connect(self.machine.pulse_peener)
        self.actionPulse_Peener_Until_Up.triggered.connect(lambda: self.machine.pulse_peener_until_up(False))
        self.actionStop_Peener.triggered.connect(lambda: self.machine.pwm.start(0))

        # Machine Settings
        self.actionDry_Run_Only.triggered.connect(self.update_settings_from_ui)

        # Canvas Buttons
        self.clearButton.clicked.connect(self.clear_canvas)
        self.undoButton.clicked.connect(self.canvas.undo_path)
        self.redoButton.clicked.connect(self.canvas.redo_path)
        self.drawBorderButton.clicked.connect(self.update_settings_from_ui)
        self.smoothPathsButton.clicked.connect(self.canvas.smooth_paths)
        self.autoSizeButton.clicked.connect(lambda *a, **k: self.do_background_process(
            "Auto Sizing Drawing",
            "Auto Sizing Drawing, Please Wait...",
            self.canvas.auto_size_paths
        ))
        self.optimizeButton.clicked.connect(lambda *a, **k: self.do_background_process(
            "Optimize Path Order",
            "Optimizing Path Order, Please Wait...",
            self.canvas.optimize_path_order
        ))
        self.designSelectBox.currentTextChanged.connect(self.load_premade_design)

        # self.autoSizeButton.hide()

        # Control Buttons
        self.sendButton.clicked.connect(self.on_send_to_dotter)

        # Styling
        self.sendButton.setAutoFillBackground(True)
        self.sendButton.setStyleSheet("QPushButton { background-color: blue; }")
        self.clearButton.setAutoFillBackground(True)
        self.clearButton.setStyleSheet("QPushButton { background-color: red; }")

        # Connect Events
        self.settings_changed.connect(self.canvas.update_settings)
        self.settings_changed.connect(self.machine.update_settings)
        self.machine.routine_dialog_event.connect(self.dialog_event_handler)
        self.machine.report_machine_position.connect(lambda pos: self.canvas.update_machine_pos([e / self.settings['tag_diam'] for e in pos]))

        if self.FULL_SCREEN:
            if self.HIDE_TITLEBAR:
                self.setWindowFlag(Qt.FramelessWindowHint)
                self.setAttribute(Qt.WA_TranslucentBackground)
            self.showMaximized()
        else:
            self.show()

    def load_settings_from_file(self):
        if os.path.isfile(self.SETTINGS_FP):
            with open(self.SETTINGS_FP) as settings_file:
                new_settings = json.load(settings_file)
                new_ver = new_settings['_version'] if '_version' in new_settings.keys() else None
                old_ver = self.settings['_version']
                if new_ver == old_ver:
                    self.settings.update(new_settings)
                    self.settings_changed.emit(self.settings)
                else:
                    print(f"Settings File Version too old, ignoring. v{new_ver} < v{old_ver}")

    def save_settings_to_file(self):
        with open(self.SETTINGS_FP, "w+") as settings_file:
            json.dump(self.settings, settings_file)

    def update_settings_from_ui(self):
        for key, elem in self._settings_ui:
            self.settings[key] = elem.isChecked()
        self.settings_changed.emit(self.settings)

    def on_settings_changed(self):
        for key, elem in self._settings_ui:
            elem.setChecked(self.settings[key])
        self.settings_changed.emit(self.settings)

    def dialog_event_handler(self, dialog_func, args, kwargs):
        self.machine._dialog_resp = dialog_func(self, *args, **kwargs)

    # Canvas Functions

    def save_design(self):
        if self.canvas.get_paths():
            filepath = QFileDialog.getSaveFileName(self, 'Save Custom Design', './designs', "JSON file (*.json)")
            if filepath:
                filepath = filepath[0]
                if not filepath.lower().endswith(".json"):
                    filepath += ".json"
                self.canvas.save_to_file(filepath)

    def load_design(self):
        filepath = QFileDialog.getOpenFileName(self, 'Open Design', './designs', "JSON file (*.json)")
        filepath = filepath[0]
        if filepath and os.path.isfile(filepath) and filepath.lower().endswith('.json'):
            self.canvas.load_from_file(filepath)

    def load_premade_design(self, key):
        if key and key in self.PREMADE_DESIGNS:
            filepath = self.PREMADE_DESIGNS[key]
            if filepath is not None:
                if os.path.isfile(filepath):
                    self.canvas.load_from_file(filepath)
                else:
                    print("File not found")
            self.designSelectBox.setCurrentText("Load Premade Design")
        else:
            print(f"Could not load premade design: {key}")

    def load_canvas_template(self):
        filepath = QFileDialog.getOpenFileName(self, 'Load Template Image', './')  #, "Image file (*.jpg, *.jpeg, *.png)")
        if filepath[0] and os.path.isfile(filepath[0]):
            self.canvas.load_template(filepath[0])

    def refresh_premade_designs(self):
        self.designSelectBox.clear()
        self.PREMADE_DESIGNS = dict([("Load Premade Design", None)] + [
            (".".join(fp.split("\\")[-1].split("/")[-1].split(".")[:-1]).replace("_", " ").title(), fp)
            for fp in glob.glob('designs/*.json')
        ])
        for i, (key, fp) in enumerate(self.PREMADE_DESIGNS.items()):
            icon = QIcon(fp.replace(".json", ".png")) if fp else QIcon()
            self.designSelectBox.addItem(icon, key)

    def do_background_process(self, title, msg, target, *args, **kwargs):
        print(self._background_process_dialog)
        self._background_process_dialog = QMessageBox(
            QMessageBox.Information,
            title, 
            msg
        )
        self._background_process_dialog.setStandardButtons(QMessageBox.StandardButton.NoButton)

        def run():
            target(*args, **kwargs)
            # self._background_process_dialog.hide()
            self._background_process_dialog = None
        
        self._active_process = ProcessRunnable(run)

        self._background_process_dialog.setModal(True)
        self._background_process_dialog.show()

        self._active_process.start()

    # Decorators

    def __check_canvas(action):
        def wrapper(func):
            def inner(self, *args, **kwargs):
                if len(self.canvas.get_paths()) >= 1:
                    return func(self, *args, **kwargs)
                else:
                    print("Canvas needs at least 1 line.")
                    QMessageBox.warning(self, f'Cannot {action}', f'Cannot {action}, canvas needs at least one line.')
            return inner
        return wrapper

    def __check_connection(action):
        def wrapper(func):
            def inner(self, *args, **kwargs):
                if self.settings['port']:
                    return func(self, *args, **kwargs)
                else:
                    print("Port not set.")
                    QMessageBox.warning(self, f'Aborting {action}', f'Cannot {action} specified action, serial port not set.')
            return inner
        return wrapper

    def __confirm_first(title="Confirm", msg="Continue?"):
        def wrapper(func):
            def inner(self, *args, **kwargs):
                confirm = QMessageBox.question(self, title, msg,
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Cancel
                )
                if confirm == QMessageBox.Ok:
                    return func(self, *args, **kwargs)
            return inner
        return wrapper

    # Progress Dialog Functions

    def do_progress_routine(self, title, target, *args, **kwargs):
        self._progress_dialog = QProgressDialog(
            f"{title}. Please wait...",
            "Cancel",
            0, 100,
            self
        )

        def on_progress_changed(v):
            self._progress_dialog.setValue(v)

        def on_status_changed(e):
            self._progress_dialog.setLabelText(f"{title}: {e}")

        def on_routine_done():
            if self._progress_dialog:
                self._progress_dialog.hide()
            try:
                self.machine.report_routine_progress.disconnect(on_progress_changed)
            except Exception as ex:
                print(ex)
            try:
                self.machine.report_routine_status.disconnect(on_status_changed)
            except Exception as ex:
                print(ex)
            try:
                self.machine.routine_finished.disconnect(on_routine_done)
            except Exception as ex:
                print(ex)
            self._progress_dialog = None

        self.machine.report_routine_progress.connect(on_progress_changed)
        self.machine.report_routine_status.connect(on_status_changed)
        self.machine.routine_finished.connect(on_routine_done)

        self._progress_dialog.canceled.connect(self.machine.e_stop)
        self._progress_dialog.setWindowTitle(title)
        self._progress_dialog.setModal(True)  # Disable main window GUI while dialog is open
        self._progress_dialog.show()

        self._active_process = ProcessRunnable(target, args, kwargs)
        self._active_process.start()

    # Machine Functions

    @__confirm_first("Clear Canvas", "Are you sure you want to clear the canvas?")
    def clear_canvas(self, *a, **k):
        self.canvas.clear_paths()

    @__check_connection("Write Default Settings")
    def write_machine_defaults(self, *a, **k):
        print("Writing Default GRBL Settings")
        with open('grbl_settings') as src:
            self.machine.ser_send(*src.readlines())

    @__check_connection("Home Machine")
    @__confirm_first("Home Machine", "Are you sure you want to home the machine?")
    def on_home_machine(self, *a, **k):
        self.do_progress_routine("Home Machine", self.machine.do_homing_routine)

    @__check_canvas("Peen Design")
    @__check_connection("Peen Design")
    @__confirm_first("Peen Design", "Are you sure you want to peen this design?")
    def on_send_to_dotter(self, *a, **k):
        self.do_progress_routine("Peen Design", self.machine.do_engraving_routine, self.canvas.get_paths())

class ProcessRunnable(QRunnable, QObject):
    def __init__(self, target, args=[], kwargs={}):
        QRunnable.__init__(self)
        self.t = target
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.t(*self.args, **self.kwargs)

    def start(self):
        QThreadPool.globalInstance().start(self)
