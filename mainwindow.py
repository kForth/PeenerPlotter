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
from pathlib import Path
import sys
import glob
import serial
import colorsys
import time
from multiprocessing import Process

from PyQt5 import uic
from PyQt5.QtCore import QSettings, Qt, QRunnable, QThreadPool
from PyQt5.QtWidgets import QMainWindow, QHeaderView, QTableWidgetItem, QFileDialog, QMessageBox
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QIcon

from canvas import PeenerCanvas
from machine import Machine

class MainWindow(QMainWindow):
    settings = {
        'port': '/dev/ttyAMA0',
        'tag_diam': 38 * 2,  # mm (engraveable area diameter)
        'line_width': 0.5,  # mm - Peener line width
        'engrave_speed': 500,  # mm/100/s,
        'travel_speed': 800,  # mm/100/s,
        'show_travel_lines': True,
        'colorful_paths': False,
    }

    PREMADE_DESIGNS = {
        "Load Premade Design": None
    }

    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)
        # self.setFixedSize(self.size())
        # self.setWindowFlag(Qt.FramelessWindowHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)

        self.load_settings_from_file()

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
        self.actionShow_Travel_Lines_on_Canvas.toggled.connect(self.on_settings_changed)

        # Machine Actions
        self.actionHome_Machine_2.triggered.connect(self.home_machine)
        self.actionPut_Machine_To_Sleep.triggered.connect(self.machine.connect_and_sleep)
        self.actionTest_Connection.triggered.connect(self.machine.test_connection)

        # Clamp Actions
        # self.actionOpen_Clamp.triggered.connect(self.machine.wake_and_home_clamp)
        # self.actionClose_Clamp.triggered.connect(self.machine.wake_and_close_clamp)

        # Pizza Tray Actions
        self.actionSpin_Tray_360_CCW.triggered.connect(lambda: self.machine.spin_tray(1, self.TRAY_CCW))
        self.actionSpin_Tray_360_CW.triggered.connect(lambda: self.machine.spin_tray(1, self.TRAY_CW))
        self.actionDispense_Tag_2.triggered.connect(self.machine.dispense_tag)

        # Peener Motor Actions
        self.actionPulse_Peener_Once.triggered.connect(self.machine.pulse_peener)
        self.actionPulse_Peener_Until_Up.triggered.connect(lambda: self.machine.pulse_peener_until_up(False))
        self.actionStop_Peener.triggered.connect(lambda: self.machine.pwm.start(0))

        # Canvas Buttons
        self.clearButton.clicked.connect(self.canvas.clear_canvas)
        self.undoButton.clicked.connect(self.canvas.undo_path)
        self.redoButton.clicked.connect(self.canvas.redo_path)
        self.designSelectBox.currentTextChanged.connect(self.load_premade_design)

        # Control Buttons
        self.sendButton.clicked.connect(self.machine.do_engraving_routine)
        self.stopButton.clicked.connect(self.machine.e_stop)

        # Styling
        self.sendButton.setStyleSheet("background-color : blue")
        self.stopButton.setStyleSheet("background-color : red")

        self._active_process = None

        # self.show()
        self.showMaximized()

    def on_settings_changed(self):
        self.settings['show_travel_lines'] = self.actionShow_Travel_Lines_on_Canvas.checked
        self.canvas.update_settings(self.settings)
        self.machine.update_settings(self.settings)

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

    def refresh_premade_designs(self):
        self.designSelectBox.clear()
        self.PREMADE_DESIGNS = dict([("Load Premade Design", None)] + [
            (".".join(fp.split("/")[-1].split(".")[:-1]).replace("_", " ").title(), fp)
            for fp in glob.glob('designs/*.json')
        ])
        for key in self.PREMADE_DESIGNS.keys():
            self.designSelectBox.addItem(QIcon(f'designs/{key.lower().replace(" ", "_")}.png'), key)

    def load_premade_design(self, key):
        filepath = self.PREMADE_DESIGNS[key]
        if filepath is not None:
            if os.path.isfile(filepath):
                self.canvas.load_from_file(filepath)
            else:
                print("File not found")
        self.designSelectBox.setCurrentText("Load Premade Design")

    def load_settings_from_file(self):
        pass

    def save_settings_to_file(self):
        pass

    def load_canvas_template(self):
        filepath = QFileDialog.getOpenFileName(self, 'Load Template Image', './')  #, "Image file (*.jpg, *.jpeg, *.png)")
        if filepath[0] and os.path.isfile(filepath[0]):
            self.canvas.load_template(filepath[0])

    def home_machine(self):
        self._active_process = ProcessRunnable(self.machine.do_home_routine, args=())
        self._active_process.start()

class ProcessRunnable(QRunnable):
    def __init__(self, target, args):
        QRunnable.__init__(self)
        self.t = target
        self.args = args

    def run(self):
        self.t(*self.args)

    def start(self):
        QThreadPool.globalInstance().start(self)
