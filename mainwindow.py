import os
from pathlib import Path
import sys
import glob
import serial
import colorsys
import time

from PyQt5 import uic
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QMainWindow, QHeaderView, QTableWidgetItem, QFileDialog, QMessageBox
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QIcon

from canvas import CanvasPeener
from engraver import Engraver

TESTING = True
if not TESTING:
    import RPi.GPIO as GPIO
else:
    import GPIO

class MainWindow(QMainWindow):
    settings = {
        'port': '/dev/ttyAMA0',
        'flavor': 'grbl',
        'tag_diam': int(1.125*25.4),  # mm (engraveable area diameter)
        'line_width': 0.5,  # mm - Engraver line width
        'engrave_speed': 1500,  # mm/100/s,
        'travel_speed': 5000,  # mm/100/s,
    }

    PREMADE_DESIGNS = {
        "Load Premade Design": None
    }

    DWELL = 0.1
    WORK_OFFSET = (70, -165)
    PEEN_LOW = 20
    PEEN_HIGH = 50

    ser = serial.Serial(baudrate=115200)

    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)
        # self.setFixedSize(self.size())

        self.load_settings_from_file()  # TODO: Thread this

        self.canvas = CanvasPeener(self.settings)
        self.canvas_label.parent().layout().replaceWidget(self.canvas_label, self.canvas)

        self.engraver = Engraver()

        self.load_premade_designs()
        self.designSelectBox.currentTextChanged.connect(self.load_premade_design)

        self.actionLoad_Canvas_Template.triggered.connect(self.load_canvas_template)
        self.actionClear_Canvas_Template.triggered.connect(self.canvas.clear_template)

        self.action_saveDesign.triggered.connect(self.save_design)
        self.action_loadDesign.triggered.connect(self.load_design)
        self.action_homeMachine.triggered.connect(self.home_machine)

        self.clearButton.clicked.connect(self.canvas.clear_canvas)
        self.undoButton.clicked.connect(self.canvas.undo_path)
        self.redoButton.clicked.connect(self.canvas.redo_path)
        self.sendButton.clicked.connect(self.do_engraving_routine)
        self.stopButton.clicked.connect(self.stop_peener)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(12, GPIO.OUT)
        self.pwm = GPIO.PWM(12, 1000)
        self.pwm.start(0)

        self.show()

    def on_settings_changed(self):
        self.canvas.update_settings(self.settings)

    def stop_peener(self):
        # TODO: Stop GRBL
        self.pwm.start(0)  # Turn off Peener

    def update_ser_status(self):
        self.action_connectDotter.setEnabled(not self.ser.is_open)
        self.action_disconnectDotter.setEnabled(self.ser.is_open)

    def save_design(self):
        if self.canvas.get_paths():
            filepath = QFileDialog.getSaveFileName(self, 'Save Custom Design', './designs', "JSON file (*.json)")
            self.canvas.save_to_file(filepath[0])

    def load_design(self):
        filepath = QFileDialog.getOpenFileName(self, 'Open Design', './designs', "JSON file (*.json)")
        if filepath[0] and os.path.isfile(filepath[0]) and filepath[0].endswith('.json'):
            self.canvas.load_from_file(filepath[0])

    def load_premade_designs(self):
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

    def create_settings_file(self):
        pass

    def load_canvas_template(self):
        filepath = QFileDialog.getOpenFileName(self, 'Load Template Image', './')  #, "Image file (*.jpg, *.jpeg, *.png)")
        if filepath[0] and os.path.isfile(filepath[0]):
            self.canvas.load_template(filepath[0])

    def home_machine(self):
        if not self.settings['port']:
            print("Port not set.")  # TODO: Popup Dialog
            return

        confirm = QMessageBox.question(self, 
            'Home Machine', 
            'Are you sure you want to home the machine?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        print("Homing Machine")
        try:
            print("Connecting GRBL")
            self.engraver.connect(self.settings['port'])

            print("Initializing GRBL")
            self.engraver.send_gcode(chr(24), False)  # Soft Reset
            self.engraver.send_gcode("$X", False)     # Enable
            self.engraver.send_gcode("$$")            # Print Settings

            print("Homing Axes")
            self.engraver.send_gcode("$H")  # Home all axes

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured while Homing!")
            
        finally:
            print("Disconnecting GRBL")
            self.engraver.send_gcode("$SLP")  # Sleep GRBL
            if self.engraver.is_connected():
                self.engraver.disconnect()


    def do_engraving_routine(self):
        if len(self.canvas.get_paths()) < 1:
            print("Canvas needs at least 1 line.")  # TODO: Popup Dialog
            return
        if not self.settings['port']:
            print("Port not set.")  # TODO: Popup Dialog
            return

        confirm = QMessageBox.question(self, 
            'Peen Design', 
            'Are you sure you want to peen this design?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        print("Loading Tag")
        loaded = False
        while not loaded:
            # TODO: Spin pizza tray 180deg
            confirm = QMessageBox.question(self, 
                'Peen Design', 
                'Are you sure you want to peen this design?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            loaded = confirm == QMessageBox.Yes

        print("Initializing Peener")
        try:
            print("Connecting GRBL")
            self.engraver.connect(self.settings['port'])

            print("Initializing GRBL")
            self.engraver.send_gcode(chr(24), False)  # Soft Reset
            self.engraver.send_gcode("$X", False)     # Enable
            self.engraver.send_gcode("$$")            # Print Settings

            print("Homing Axes")
            self.engraver.send_gcode("$H")  # Home all axes

            print("Initializing Motion")
            self.engraver.send_gcode([
                "G17",   # XY Plane
                "G21",   # mm mode
                "G53",   # Machine coords
                "G90"    # Absolute mode
            ])

            print("Clamping Tag")
            self.engraver.send_gcode([
                "G0 Z6.7 F100",   # Lower Clamp
                "G4 P0"           # Pause
            ])

            print("Setting Peener to slow speed")
            self.pwm.start(self.PEEN_LOW)
            time.sleep(self.DWELL)

            print("Moving into position")
            self.engraver.send_gcode([
                "G92 X70 Y165",   # Set Work origin
                "G54",            # Work coords
                "G0 X0",          # Move inline with clamp opening
                "Y16",            # Move to edge of tag
                "G4 P1"           # Pause
            ])

            pt_to_gcode = lambda x, y: "G0 X" + str(round(path[0][0] * 100, 2)) + " Y" + str(round(path[0][1] * 100, 2))

            for i, path in enumerate(self.canvas.get_paths()):
                print(f"Starting Path #{i}")

                print("  Moving to path start")
                self.engraver.send_gcode([
                    pt_to_gcode(*path[0]),  # Move to first position
                    "G4 P0"                 # Pause
                ])

                print("  Setting Peener to high speed")
                self.pwm.start(self.PEEN_HIGH)  # Set Peener to peen speed
                time.sleep(self.DWELL)

                print("  Drawing Path")
                self.engraver.send_gcode([
                    "G0 X" + str(round(pt[0] * scale, 2)) + " Y" + str(round(pt[1] * scale, 2))
                    for pt in path[1:]
                ])
                self.engraver.send_gcode(["G4 P0"])

                print("  Done, Setting Peener to low speed")
                self.pwm.start(self.PEEN_LOW)  # Set Peener to travel speed
                time.sleep(self.DWELL)

            print("Parking Peener")
            self.engraver.send_gcode([
                "G0 X0 Y0 F1000",  # Move back to center of tag
                "G53",             # Machine coods
                "Y0",              # Move out of clamp
                "X0",              # Move home
                "G4 P0"            # Pause
            ])

            print("Stopping Peener")
            self.pwm.start(0)  # Turn off Peener

            print("Releasing Clamp")
            self.engraver.send_gcode([
                "G0 Z0",  # Open Clamp
                "G4 P0"   # Pause
            ])

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured with Peening!")
            print("Stopping Peener (EX)")
            self.pwm.start(0)
            
        finally:
            print("Disconnecting GRBL")
            self.engraver.send_gcode("$SLP")  # Sleep GRBL
            if self.engraver.is_connected():
                self.engraver.disconnect()

        print("Dispensing Tag")
        # TODO: Spin pizza tray 180deg

        print("Done")

