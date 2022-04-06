
import time
import platform
import traceback

if any([e in platform.platform().lower() for e in ["macos", "windows"]]):
    import FakeGPIO as GPIO
else:
    import RPi.GPIO as GPIO

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from proto_serial import ProtoSerial
from util import *

class Machine(QObject):
    # GUI Signals
    routine_started = pyqtSignal(object)
    routine_finished = pyqtSignal(object)
    report_routine_progress = pyqtSignal(object)
    report_routine_status = pyqtSignal(object)
    report_machine_position = pyqtSignal(object)

    routine_dialog_event = pyqtSignal(object, object, object)

    # General Settings
    DWELL = 0.1  # General wait time, mostly used after changing speed.

    # Coordinates
    WORK_OFFSET = (65, 162)  # Offset to center of tag
    ENTRY_POINT = (0, -36)  # Point of entry for tag (relative to center of tag).
    PRE_ENTRY_POINT = (0, -50)  # Point to move to after peening before opening clamp and dispensing tag (relative to center of tag)

    # Peener Settings
    PEEN_LOW = 20  # % Speed for travel moves
    PEEN_HIGH = 50  # % Speed for peening moves
    PULSE_DELAY = 0.3 # Seconds to turn motor on when trying to lift

    # Gantry Settings
    GANTRY_PARK_POS = (0, 0, 0)
    GANTRY_TRAVEL_SPEED = 800
    GANTRY_PEEN_SPEED = 500

    # Clamp Settings
    CLAMP_OPEN_POS = 0
    CLAMP_PARTIAL_POS = 6
    CLAMP_CLOSE_POS = 10.5

    # BCM Pin Numbering
    PEENER_PIN = 12
    TRAY_DIR_PIN = 16
    TRAY_STEP_PIN = 20
    TRAY_LIMIT_PIN = 21

    # Tray Movement
    TRAY_REV_DIST = 3200  # Number of steps for 1 revolution (200 steps/rev * 16 microstepping)
    TRAY_CCW = 1  # Bit value for CCW movement.
    TRAY_CW = 0  # Bit value for CW movement.
    TRAY_SPEED = 1000  # Step Freqeuncy Hz
    TRAY_HOME_SPEED = 500   # Step Freqeuncy Hz

    # GRBL Commands
    GRBL_RESET = chr(24)
    GRBL_ENABLE = "$X"
    GRBL_HOLD = "!"
    GRBL_HOME_ALL = "$H"
    GRBL_HOME_X = "$HX"
    GRBL_HOME_Y = "$HY"
    GRBL_HOME_Z = "$HZ"
    GRBL_PRINT_SETTINGS = "$$"
    GRBL_STATUS = "?"
    GRBL_IDLE_HOLD_ON = "$1=255"
    GRBL_IDLE_HOLD_OFF = "$1=10"
    GRBL_SLEEP = "$SLP"
    GRBL_SET_TAG_OFFSET = f"G92 X-{WORK_OFFSET[0]} Y-{WORK_OFFSET[1]}"
    GRBL_MACHINE_REL_COORDS = "G52 X0 Y0"  # Coordinates relative to machine origin
    GRBL_TAG_REL_CORRDS = "G54"  # Coordiantes releative to tag center

    GRBL_TRAVEL_XYZ = lambda self, x, y, z: f"G0 X{x} Y{y} Z{z}"
    GRBL_TRAVEL_XY = lambda self, x, y: f"G0 X{x} Y{y}"
    GRBL_TRAVEL_X = lambda self, x: f"G0 X{x}"
    GRBL_TRAVEL_Y = lambda self, y: f"G0 Y{y}"
    GRBL_TRAVEL_Z = lambda self, z: f"G0 Z{z}"
    GRBL_PEEN_XY = lambda self, x, y: f"G1 X{x} Y{y} F{self.GANTRY_PEEN_SPEED}"  # f"G0 X{x} Y{y}"

    GRBL_PARK_ALL = GRBL_TRAVEL_XYZ(None, *GANTRY_PARK_POS)
    GRBL_CLOSE_CLAMP = GRBL_TRAVEL_Z(None, CLAMP_CLOSE_POS)
    GRBL_OPEN_CLAMP = GRBL_TRAVEL_Z(None, CLAMP_OPEN_POS)
    GRBL_OPEN_CLAMP_PARTIAL = GRBL_TRAVEL_Z(None, CLAMP_PARTIAL_POS)

    def __init__(self, window, settings):
        QObject.__init__(self)
        self.window = window
        self.settings = settings

        # Init Util Variables
        self._routine_progress = 0
        self._should_stop = False

        # Init Serial Connection Manager
        self.ser = ProtoSerial()

        # Init GPIO to GBCM Pin Mode - use IO numbers, not physical pin numbers
        # https://community.element14.com/cfs-file/__key/telligent-evolution-components-attachments/13-153-00-00-00-01-74-28/pi3_5F00_gpio.png
        GPIO.setmode(GPIO.BCM)

        # Setup Peener motor PWM Output
        GPIO.setup(self.PEENER_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(self.PEENER_PIN, 1000)
        self.pwm.start(0)

        # Setup Pizza Tray Pins
        GPIO.setup(self.TRAY_LIMIT_PIN, GPIO.IN)
        GPIO.setup(self.TRAY_DIR_PIN, GPIO.OUT)
        GPIO.setup(self.TRAY_STEP_PIN, GPIO.OUT)
        GPIO.output(self.TRAY_DIR_PIN, 1)

    def update_settings(self, settings):
        self.settings = settings
    
    def _check_should_stop(self):
        if self._should_stop:
            self._should_stop = False
            raise _CancelRoutineExpcetion()

    def _connect(self, enable=True):
        self._was_connected = self.ser.is_connected()
        if not self._was_connected:
            self._set_status("Connecting GRBL")
            self.ser.connect(self.settings['port'])

            self._set_status("Initializing GRBL")
            self.ser.send(self.GRBL_RESET, False)
            self.ser.send([
                self.GRBL_PRINT_SETTINGS,
                self.GRBL_IDLE_HOLD_OFF
            ])
            if(enable):
                self.ser.send(self.GRBL_ENABLE)
            time.sleep(self.DWELL)
        
    def _disconnect(self):
        if self.ser.is_connected():
            self.ser.disconnect()
        self._was_connected = False

    def _disconnect_if_wasnt(self):
        if self.ser.is_connected() and not self._was_connected:
            self.ser.disconnect()
    
    def _sleep(self):
        if self.ser.is_connected():
            self._set_status("Putting GRBL to Sleep")
            self.ser.send(self.GRBL_SLEEP)
        
    def __func_to_name(self, func_name):
        return func_name.replace("_", " ").title()[(3 if func_name[:3] == "do_" else 0):]

    # GUI Event Functions    
    
    def get_dialog_response(self, dialog, *args, **kwargs):
        self._dialog_resp = None
        self.routine_dialog_event.emit(dialog, args, kwargs)
        while self._dialog_resp is None:
            time.sleep(0.5)
        return self._dialog_resp

    def _reset_progress(self, status="Ready"):
        self._set_progress(0, status)
    
    def _increment_progress(self, amount, status=None):
        self._set_progress(self._routine_progress + amount, status)

    def _set_progress(self, progress, status=None):
        self._routine_progress = max(0, min(100, int(progress)))
        self.report_routine_progress.emit(self._routine_progress)
        if status:
            self._set_status(status)
        self._check_should_stop()

    def _set_status(self, status):
        self._routine_status = status
        status_str = f"{self._routine_name}: {self._routine_status}"
        print(status_str)
        self.report_routine_status.emit(status_str)
        self._check_should_stop()

    # Decorators

    def __as_routine(name):
        def wrapper(func):
            def inner(self, *args, **kwargs):
                self._routine_name = name
                self._set_progress(0, f"Starting")
                self.routine_started.emit(name)
                result = func(self, *args, **kwargs)
                self.routine_finished.emit(result)
                self.routine_dialog_event.emit(
                    QMessageBox.information, [
                        f"{self._routine_name} Finished",
                        f"{self._routine_name} has finished!",
                        QMessageBox.Ok
                    ], {}
                )
                return result
            return inner
        return wrapper
    
    def __with_connection(func):
        def wrapper(self, *args, **kwargs):
            self._reset_progress()
            result = None
            try:
                self._set_progress(1, "Connecting")
                self._connect()

                self._set_progress(2, "Resetting GRBL")
                self.ser.send(self.GRBL_RESET, False)

                self._set_progress(5, "GRBL Ready")
                result = func(self, *args, **kwargs)
            except _CancelRoutineExpcetion as ex:
                self._set_status("Cancelled")
                # result = ex
            except Exception as ex:
                traceback.print_exc()

                self._set_status("Error")
                self.e_stop()
                self.routine_dialog_event.emit(QMessageBox.critical, [
                    "Error While Peening", 
                    "An Error occured while Peening. Machine has been stopped for safety."
                ], {})

                # result = ex
            finally:
                self.pwm.start(0)
                self.ser.send(self.GRBL_IDLE_HOLD_OFF)
                self._sleep()
                self._disconnect_if_wasnt()
                if result is not None:
                    self._set_progress(100, "Done")
            return result
        return wrapper

    def e_stop(self):
        print("E-Stop")
        self._should_stop = True
        self.pwm.start(0)  # Turn off Peener
        self._connect(False)
        self.ser.send([
            self.GRBL_HOLD,
            self.GRBL_IDLE_HOLD_OFF,
            self.GRBL_SLEEP
        ])

    def get_machine_status(self):
        self._connect(False)
        yield self.ser.send(self.GRBL_STATUS)
        self._disconnect_if_wasnt()

    def _wait_for_idle(self):
        print("Waiting for Idle")
        status = []
        while not any(["Idle" in e for e in status]):
            time.sleep(0.25)
            status = self.get_machine_status()
    
    # Tray Util Functions

    def spin_tray(self, revolutions=1, direction=TRAY_CCW):
        print(f"Spinning Tray {revolutions=} {direction=}")
        GPIO.output(self.TRAY_DIR_PIN, direction)
        for _ in range(int(self.TRAY_REV_DIST * revolutions)):
            GPIO.output(self.TRAY_STEP_PIN, GPIO.HIGH)
            time.sleep(1 / self.TRAY_SPEED)
            GPIO.output(self.TRAY_STEP_PIN, GPIO.LOW)
            time.sleep(1 / self.TRAY_SPEED)

    def home_tray(self, direction=TRAY_CCW):
        print("Homing Tray")
        GPIO.output(self.TRAY_DIR_PIN, direction)
        while GPIO.input(self.TRAY_LIMIT_PIN):
            GPIO.output(self.TRAY_STEP_PIN, GPIO.HIGH)
            time.sleep(1 / self.TRAY_HOME_SPEED)
            GPIO.output(self.TRAY_STEP_PIN, GPIO.LOW)
            time.sleep(1 / self.TRAY_HOME_SPEED)

    def load_tag(self, err_on_cancel=True):
        print("Loading Tag")
        self.spin_tray(1, self.TRAY_CCW)

        resp = self.get_dialog_response(
            QMessageBox.question,
            'Loading Tag', 
            'Did the tag load correctly?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if resp == QMessageBox.Cancel:
            if err_on_cancel:
                raise _CancelRoutineExpcetion()
            else:
                return False
        elif resp == QMessageBox.No:
            self.load_tag()
        else:
            return True

    def dispense_tag(self):
        print("Dispensing Tag")
        self.spin_tray(0.25, self.TRAY_CCW)  # Spin tray 1/4 rev CCW to dispense tag
        time.sleep(self.DWELL)
        self.spin_tray(0.25, self.TRAY_CW)  # Spin tray 1/4 rev CW to park tray
        time.sleep(self.DWELL)

    # Peener Util Functions

    def pulse_peener(self):
        print("Pulsing Peener")
        self.pwm.start(self.PEEN_HIGH)  # Briefly turn on peener motor
        time.sleep(self.PULSE_DELAY)
        self.pwm.start(0)  # Turn back off
        time.sleep(self.PULSE_DELAY * 2)  # Wait for deceleration

    def pulse_peener_until_up(self, err_on_cancel=True):
        self.pulse_peener()
        resp = self.get_dialog_response(
            QMessageBox.question,
            'Stopping Peener', 
            'Is the peener lifted off the tag?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if resp == QMessageBox.Cancel:
            if err_on_cancel:
                raise _CancelRoutineExpcetion()
            else:
                return False
        elif resp == QMessageBox.No:
            self.pulse_peener_until_up()
        else:
            return True

    # Routines

    @__as_routine("Connect & Sleep Routine")
    @__with_connection
    def connect_and_sleep(self):
        self._set_progress(10, "Putting GRBL to Sleep")
        self._sleep()
        self._set_progress(100, "Done")
        return self.ser.is_connected()

    @__as_routine("Homing Routine")
    @__with_connection
    def do_homing_routine(self):
        self._set_progress(10, "Homing Clamp (Z)")
        self.ser.send(self.GRBL_HOME_Z)
        self._wait_for_idle()
        self._set_progress(25, "Clamp Homed")
        time.sleep(1)

        self._set_progress(30, "Homing X Axis")
        self.ser.send(self.GRBL_HOME_X)
        self._wait_for_idle()
        self._set_progress(50, "X Axis Homed")
        time.sleep(1)

        self._set_progress(55, "Homing Y Axis")
        self.ser.send(self.GRBL_HOME_Y)
        self._wait_for_idle()
        self._set_progress(75, "Y Axis Homed")
        time.sleep(1)

        # self._set_progress(80, "Homing Tray")
        # self.home_tray()
        self._set_progress(100, "Homing Done")
        time.sleep(1)
        return True
    
    @__as_routine("Engraving Routine")
    @__with_connection
    def do_engraving_routine(self, paths):
        self._set_progress(6, "Homing Machine")
        self.ser.send(self.GRBL_HOME_ALL)
        self._wait_for_idle()
        self._set_progress(7, "Homing Done")

        self._set_progress(9, "Initializing Motion")
        self.ser.send([
            self.GRBL_SET_TAG_OFFSET,
            self.GRBL_IDLE_HOLD_ON,
            "G17",  # XY Plane
            "G21",  # mm mode
            "G90",  # Absolute coord mode
            self.GRBL_MACHINE_REL_COORDS,
            self.GRBL_ENABLE,
            # self.GRBL_TRAVEL_Z(1)  # Move clamp up a litte (really just to activate servos to let tray spin)
        ])
        time.sleep(self.DWELL)

        self._set_progress(10, "Loading Tag")
        self.load_tag()

        self._set_progress(12, "Clamping Tag")
        self.ser.send(self.GRBL_CLOSE_CLAMP)
        self._wait_for_idle()

        self._set_progress(15, "Moving To Tag")
        self.ser.send([
            self.GRBL_TAG_REL_CORRDS,
            self.GRBL_TRAVEL_XY(*self.PRE_ENTRY_POINT),  # Move towards tag
            self.GRBL_TRAVEL_XY(*self.ENTRY_POINT)  # Move into tag area
        ])

        # Path points are between -0.5 and 0.5 represnting +/- 50% of engraveable area, multiple by the tag diameter to scale up.
        # Also round to 2 decimal places to clean it up.
        scale = self.settings['tag_diam']
        scale_pt = lambda pts: [round(e * scale, 2) for e in pts] 

        prog_after_paths = 80
        prog_per_path = (prog_after_paths - self._routine_progress) / (len(paths) + 1)
        for i, path in enumerate(paths):
            self._set_status(f"Drawing Path #{i}")

            print("  Moving to path start")
            self.ser.send(self.GRBL_TRAVEL_XY(*scale_pt(path[0])))  # Move to first position
            self._wait_for_idle()
            self._increment_progress(prog_per_path)

            print("  Setting Peener to High Speed")
            self.pwm.start(self.PEEN_HIGH)  # Set Peener to peen speed
            time.sleep(self.DWELL)

            print("  Drawing Path")
            self.ser.send([
                self.GRBL_PEEN_XY(*scale_pt(pt))  # Draw each point of the path
                for pt in path[1:]  # Skip the first point because we're already there
            ])
            self._wait_for_idle()

            print("  Done Path, Setting Peener to Low Speed")
            self.pwm.start(self.PEEN_LOW)  # Set Peener to travel speed
            time.sleep(self.DWELL)

        self._set_progress(prog_after_paths, "Stopping Peener")
        self.pwm.start(0)  # Turn off Peener
        time.sleep(self.DWELL)

        self._set_progress(82, "Lifting Peener")
        self.pulse_peener_until_up()

        self._set_progress(85, "Moving Off Tag")
        self.ser.send([
            self.GRBL_TRAVEL_XY(*self.ENTRY_POINT),  # Move back to entry point
            self.GRBL_TRAVEL_XY(*self.PRE_ENTRY_POINT),  # Move out of tag area
            self.GRBL_OPEN_CLAMP_PARTIAL
        ])
        self._wait_for_idle()

        self._set_progress(90, "Dispensing Tag")
        self.dispense_tag()

        self._set_progress(95, "Parking Machine")
        self.ser.send(self.GRBL_PARK_ALL)  # Park Gantry
        self._wait_for_idle()

        self._set_progress(100, "Done")

class _CancelRoutineExpcetion(Exception):
    pass
