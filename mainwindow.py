"""
TODO:
- Pizza tray stepper motors
- Peener stow position? (instead of just slow peening)
- Popup window for premade designs (or better dropdown selector?)
- Proper scaling
- Error recovery?
- Canvas linewidth?
- Canvas travel lines toggle
- Test Connection button
"""

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
from proto_serial import ProtoSerial

import platform
print(platform.platform().lower())
if "macos" in platform.platform().lower():
    print("Running on MacOS")
    import FakeGPIO as GPIO
else:
    print("Running on actual Pi")
    import RPi.GPIO as GPIO

class MainWindow(QMainWindow):
    settings = {
        'port': '/dev/ttyAMA0',
        'flavor': 'grbl',
        'tag_diam': int(1.125*25.4),  # mm (engraveable area diameter)
        'line_width': 0.5,  # mm - ProtoSerial line width
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

    # BCM Pin Numbering
    PEENER_PIN = 12
    TRAY_DIR_PIN = 16
    TRAY_STEP_PIN = 20

    TRAY_REV_DIST = 3200

    def __init__(self):
        super().__init__()
        uic.loadUi('mainwindow.ui', self)
        # self.setFixedSize(self.size())

        self.load_settings_from_file()  # TODO: Thread this

        self.canvas = CanvasPeener(self.settings)
        self.canvas_label.parent().layout().replaceWidget(self.canvas_label, self.canvas)

        self.protoneer = ProtoSerial()

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

        # Setup Peener motor PWM Output
        GPIO.setup(self.PEENER_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(self.PEENER_PIN, 1000)
        self.pwm.start(0)

        # Setup Pizza tray Stepper Output
        GPIO.setup(self.TRAY_DIR_PIN, GPIO.OUT)
        GPIO.setup(self.TRAY_STEP_PIN, GPIO.OUT)
        GPIO.output(self.TRAY_DIR_PIN, 1)

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
            QMessageBox.No | QMessageBox.Yes,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        print("Homing Machine")
        try:
            print("Connecting GRBL")
            self.protoneer.connect(self.settings['port'])

            print("Initializing GRBL")
            self.protoneer.send_gcode(chr(24), False)  # Soft Reset
            self.protoneer.send_gcode("$X", False)     # Enable
            self.protoneer.send_gcode("$$")            # Print Settings

            print("Homing Axes")
            self.protoneer.send_gcode("$H")  # Home all axes

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured while Homing!")
            
        finally:
            print("Disconnecting GRBL")
            self.protoneer.send_gcode("$SLP")  # Sleep GRBL
            if self.protoneer.is_connected():
                self.protoneer.disconnect()

    def spin_tray(self, revolutions=1, direction=0):
            GPIO.output(self.TRAY_DIR_PIN, direction)  # 1 = CW, 0 = CCW
            for _ in range(int(self.TRAY_REV_DIST * revolutions)):
                GPIO.output(self.TRAY_STEP_PIN, GPIO.HIGH)
                time.sleep(.001)
                GPIO.output(self.TRAY_STEP_PIN, GPIO.LOW)
                time.sleep(.001)

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
            QMessageBox.No | QMessageBox.Yes,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        print("Initializing Peener")
        try:
            print("Connecting GRBL")
            self.protoneer.connect(self.settings['port'])

            print("Initializing GRBL")
            self.protoneer.send_gcode(chr(24), False)  # Soft Reset
            self.protoneer.send_gcode("$X", False)     # Enable
            self.protoneer.send_gcode("$$")            # Print Settings

            print("Homing Axes")
            self.protoneer.send_gcode([
                "$H",              # Home all axes
                "G92 X-55 Y-150",  # Set Work origin
            ])

            self.protoneer.send_gcode("$X", False)     # Enable
            self.protoneer.send_gcode("$$")            # Print Settings

            print("Initializing Motion")
            self.protoneer.send_gcode([
                "G17",   # XY Plane
                "G21",   # mm mode
                "G53",   # Machine coords
                "G90",   # Absolute mode
                "G0 Z1",
                "G4 P0"
            ])

            print("Loading Tag")
            loaded = False
            while not loaded:
                self.spin_tray(1, 1)

                loaded = QMessageBox.question(self, 
                    'Loading Tag', 
                    'Did the tag load correctly?',
                    QMessageBox.No | QMessageBox.Yes,
                    QMessageBox.No
                ) == QMessageBox.Yes

            print("Clamping Tag")
            self.protoneer.send_gcode([
                "G0 Z10.5",   # Lower Clamp
                "G4 P0"       # Pause
            ])

            print("Setting Peener to slow speed")
            self.pwm.start(self.PEEN_LOW)
            time.sleep(self.DWELL)

            print("Moving into position")
            self.protoneer.send_gcode([
                "G54",            # Work coords
                "G0 X0",          # Move inline with clamp opening
                "Y16",            # Move to edge of tag
                "G4 P1"           # Pause
            ])

            pt_to_gcode = lambda x, y: "G0 X" + str(round(path[0][0] * 100, 2)) + " Y" + str(round(path[0][1] * 100, 2))

            for i, path in enumerate(self.canvas.get_paths()):
                print(f"Starting Path #{i}")

                print("  Moving to path start")
                self.protoneer.send_gcode([
                    pt_to_gcode(*path[0]),  # Move to first position
                    "G4 P0"                 # Pause
                ])

                print("  Setting Peener to high speed")
                self.pwm.start(self.PEEN_HIGH)  # Set Peener to peen speed
                time.sleep(self.DWELL)

                print("  Drawing Path")
                scale = 100
                self.protoneer.send_gcode([
                    "G0 X" + str(round(pt[0] * scale, 2)) + " Y" + str(round(pt[1] * scale, 2))
                    for pt in path[1:]
                ])
                self.protoneer.send_gcode(["G4 P0"])

                print("  Done, Setting Peener to low speed")
                self.pwm.start(self.PEEN_LOW)  # Set Peener to travel speed
                time.sleep(self.DWELL)

            print("Parking Peener")
            self.protoneer.send_gcode([
                "G0 X0 Y0",  # Move back to center of tag
                "Y-150",
                "X-55",
                "G4 P0"            # Pause
            ])

            print("Stopping Peener")
            self.pwm.start(0)  # Turn off Peener

            print("Releasing Clamp")
            self.protoneer.send_gcode([
                "G0 Z0",  # Open Clamp
                "G4 P0"   # Pause
            ])

            self.spin_tray(0.25, 1)
            self.spin_tray(0.25, 0)

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured with Peening!")
            print("Stopping Peener (EX)")
            self.pwm.start(0)
            
        finally:
            print("Disconnecting GRBL")
            self.protoneer.send_gcode("$SLP")  # Sleep GRBL
            if self.protoneer.is_connected():
                self.protoneer.disconnect()

        print("Dispensing Tag")
        # TODO: Spin pizza tray 180deg

        print("Done")

