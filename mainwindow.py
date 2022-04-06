"""
TODO:
- Stop Button
- Peener stow position? (instead of just slow peening)
- Popup window for premade designs (or better dropdown selector?)
- Error recovery? - Just use bCNC or CNC.js
- Canvas linewidth?
- Implement Speeds
- Tune Speeds
- Tune Currents
- Constant serial connection
- Machine status
- Routine progress
- Thread routine so GUI doesn't freeze
"""

import os
import glob
import json
from typing import Union

from PyQt5 import uic
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QProgressDialog
from PyQt5.QtGui import QIcon

from canvas import PeenerCanvas
from machine import Machine
from util import *

class MainWindow(QMainWindow):
    settings_changed = pyqtSignal(object)

    settings = {
        'port': '/dev/ttyAMA0',
        'tag_diam': 38 * 2,  # mm (engraveable area diameter)
        'line_width': 0.5,  # mm - Peener line width
        'show_travel_lines': True,
        'colorful_paths': False,
        'show_machine_pos': True
    }

    PREMADE_DESIGNS = {
        "Load Premade Design": None
    }

    SETTINGS_FP = "_settings.json"

    FULL_SCREEN = False
    HIDE_TITLEBAR = False

    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)
        
        self._active_process = None

        self.load_settings_from_file()
        self.save_settings_to_file()

        # Init Custom Path Drawing Widget
        self.canvas = PeenerCanvas(self.settings)
        self.canvas_label.parent().layout().replaceWidget(self.canvas_label, self.canvas)

        # Init Machine
        self.machine = Machine(self, self.settings)

        self.refresh_premade_designs()

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
        self.actionPut_Machine_To_Sleep.triggered.connect(self.machine.connect_and_sleep)

        # Clamp Actions
        # self.actionOpen_Clamp.triggered.connect(self.machine.wake_and_home_clamp)
        # self.actionClose_Clamp.triggered.connect(self.machine.wake_and_close_clamp)

        # Pizza Tray Actions
        self.actionSpin_Tray_360_CCW.triggered.connect(lambda: self.machine.spin_tray(1, self.TRAY_CCW))
        self.actionSpin_Tray_360_CW.triggered.connect(lambda: self.machine.spin_tray(1, self.TRAY_CW))
        self.actionDispense_Tag.triggered.connect(self.machine.dispense_tag)
        # self.actionHome_Tray.triggered.connect(self.machine.home_tray)

        # Peener Motor Actions
        self.actionPulse_Peener_Once.triggered.connect(self.machine.pulse_peener)
        self.actionPulse_Peener_Until_Up.triggered.connect(lambda: self.machine.pulse_peener_until_up(False))
        self.actionStop_Peener.triggered.connect(lambda: self.machine.pwm.start(0))

        # Canvas Buttons
        self.clearButton.clicked.connect(self.canvas.clear_canvas)
        self.undoButton.clicked.connect(self.canvas.undo_path)
        self.redoButton.clicked.connect(self.canvas.redo_path)
        self.optimizeButton.clicked.connect(self.on_optimize_paths)
        self.designSelectBox.currentTextChanged.connect(self.load_premade_design)

        # Control Buttons
        self.sendButton.clicked.connect(self.on_send_to_dotter)
        self.stopButton.clicked.connect(self.machine.e_stop)

        # Styling
        self.sendButton.setStyleSheet("background-color : blue")
        self.stopButton.setStyleSheet("background-color : red")

        # Connect Events
        self.settings_changed.connect(self.canvas.update_settings)
        self.settings_changed.connect(self.machine.update_settings)
        self.machine.routine_dialog_event.connect(self._handle_routine_dialog)
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
                self.settings.update(json.load(settings_file))

    def save_settings_to_file(self):
        with open(self.SETTINGS_FP, "w+") as settings_file:
            json.dump(self.settings, settings_file)

    def update_settings_from_ui(self):
        self.settings['show_travel_lines'] = self.actionShow_Travel_Lines.isChecked()
        self.settings['colorful_paths'] = self.actionShow_Colorful_Paths.isChecked()

    def on_settings_changed(self):
        self.actionShow_Travel_Lines.setChecked(self.settings['show_travel_lines'])
        self.actionShow_Colorful_Paths.setChecked(self.settings['colorful_paths'])
        self.settings_changed.emit(self.settings)

    # Canvas Functions

    def save_design(self):
        if self.canvas.get_paths():
            filepath = QFileDialog.getSaveFileName(self, 'Save Custom Design', './designs', "JSON file (*.json)")
            if filepath[-5].lower() != ".json":
                filepath += ".json"
            self.canvas.save_to_file(filepath[0])

    def load_design(self):
        filepath = QFileDialog.getOpenFileName(self, 'Open Design', './designs', "JSON file (*.json)")
        if filepath[0] and os.path.isfile(filepath[0]) and filepath[0].endswith('.json'):
            self.canvas.load_from_file(filepath[0])

    def load_premade_design(self, key):
        if key:
            filepath = self.PREMADE_DESIGNS[key]
            if filepath is not None:
                if os.path.isfile(filepath):
                    self.canvas.load_from_file(filepath)
                else:
                    print("File not found")
            self.designSelectBox.setCurrentText("Load Premade Design")

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
        for i, key in enumerate(self.PREMADE_DESIGNS.keys()):
            icon = QIcon(f'designs/{key.lower().replace(" ", "_")}.png')
            self.designSelectBox.addItem(icon, key)

    def on_optimize_paths(self):
        self.optimize_path_dialog = QMessageBox(
            QMessageBox.Information,
            'Optimizing Paths', 
            'Optimizing path order to minimize travel. Please wait...'
        )
        self.optimize_path_dialog.setStandardButtons(QMessageBox.StandardButton.NoButton)

        def optimize_paths():
            self.canvas.optimize_path_order()
            # self.optimize_path_dialog.hide()
            self.optimize_path_dialog = None
        self._active_process = ProcessRunnable(optimize_paths)

        self.optimize_path_dialog.setModal(True)
        self.optimize_path_dialog.buttonClicked.connect(lambda: QThreadPool.globalInstance().terminate(self._active_process))
        self.optimize_path_dialog.show()

        self._active_process.start()
        
    # Machine Functions

    def _handle_routine_dialog(self, dialog, args, kwargs):
        self.machine._dialog_resp = dialog(self, *args, **kwargs)

    def _can_connect_to_machine(self):
        if not self.settings['port']:
            print("Port not set.")
            QMessageBox.warning(self, 'Cannot Peen Design', 'Port not set.')
            return False
        return True

    def on_home_machine(self):
        if not self._can_connect_to_machine():
            return

        confirm = QMessageBox.question(self, 
            'Home Machine', 
            'Are you sure you want to home the machine?',
            QMessageBox.No | QMessageBox.Yes,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        dialog = QProgressDialog(
            "Homing Machine. Please wait...",
            "Cancel",
            0, 100,
            self
        )
        dialog.setWindowTitle("Homing Machine")
        self.machine.report_routine_progress.connect(dialog.setValue)
        self.machine.report_routine_status.connect(dialog.setInformativeText)
        self.machine.routine_finished.connect(lambda e: dialog.hide())
        dialog.canceled.connect(self.machine.e_stop)
        dialog.setModal(True)
        dialog.show()

        self._active_process = ProcessRunnable(self.machine.do_homing_routine)
        self._active_process.start()
                
    def on_send_to_dotter(self):
        if not self._can_connect_to_machine():
            return

        if len(self.canvas.get_paths()) < 1:
            print("Canvas needs at least 1 line.")
            QMessageBox.warning(self, 'Cannot Peen Design', 'Cannot peen design, canvas needs at least one line.')
            return

        confirm = QMessageBox.question(self, 
            'Peen Design', 
            'Are you sure you want to peen this design?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        dialog = QProgressDialog(
            "Peening Design. Please wait...",
            "Cancel",
            0, 100,
            self
        )
        dialog.setWindowTitle("Peening Design")
        self.machine.report_routine_progress.connect(lambda e: dialog.setValue(e))
        self.machine.report_routine_status.connect(lambda e: dialog.setLabelText(f"Peening Design. Please wait...\n{e}"))
        self.machine.routine_finished.connect(lambda e: dialog.hide())
        dialog.canceled.connect(self.machine.e_stop)
        dialog.setModal(True)
        dialog.show()

        self._active_process = ProcessRunnable(self.machine.do_engraving_routine, [self.canvas.get_paths()])
        self._active_process.start()

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
