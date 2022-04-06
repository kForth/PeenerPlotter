
import platform

if "macos" in platform.platform().lower():
    import FakeGPIO as GPIO
else:
    import RPi.GPIO as GPIO

from PyQt5.QtWidgets import QMessageBox

from proto_serial import ProtoSerial

class Machine:

    DWELL = 0.1
    WORK_OFFSET = (65, 162)
    ENTRY_POINT = (0, -16)
    PEEN_LOW = 20
    PEEN_HIGH = 50

    # BCM Pin Numbering
    PEENER_PIN = 12
    TRAY_DIR_PIN = 16
    TRAY_STEP_PIN = 20

    TRAY_REV_DIST = 3200
    TRAY_CCW = 1
    TRAY_CW = 0

    GRBL_RESET = chr(24)

    def __init__(self, window, settings):
        self.window = window
        self.settings = settings

        # Init Serial Connection Manager
        self.protoneer = ProtoSerial()

        # Init GPIO to GBCM Pin Mode - use IO numbers, not physical pin numbers
        GPIO.setmode(GPIO.BCM)

        # Setup Peener motor PWM Output
        GPIO.setup(self.PEENER_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(self.PEENER_PIN, 1000)
        self.pwm.start(0)

        # Setup Pizza tray Stepper Output
        GPIO.setup(self.TRAY_DIR_PIN, GPIO.OUT)
        GPIO.setup(self.TRAY_STEP_PIN, GPIO.OUT)
        GPIO.output(self.TRAY_DIR_PIN, 1)

    def update_settings(self, settings):
        self.settings = settings

    def e_stop(self):
        self.pwm.start(0)  # Turn off Peener
        if self.protoneer.is_connected():
            self.protoneer.send_gcode([
                self.GRBL_RESET,  # Soft Reset
                "!",  # Cyclehold
                "$1=0",  # Steppers off when Idle
                "$SLP"  # Sleep GRBL
            ])
        # TODO: Force quit routine

    def do_home_routine(self):
        if not self.settings['port']:
            print("Port not set.")  # TODO: Popup Dialog
            return

        QMetaObject.invokeMethod(log,
            "append", Qt.QueuedConnection, 
            Q_ARG(str, text)
        )
        confirm = QMessageBox.question(self.window, 
            'Home Machine', 
            'Are you sure you want to home the machine?',
            QMessageBox.No | QMessageBox.Yes,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        was_connected = self.protoneer.is_connected()

        print("Homing Machine")
        try:
            if not was_connected:
                print("Connecting GRBL")
                self.protoneer.connect(self.settings['port'])

            print("Initializing GRBL")
            self.protoneer.send_gcode(self.GRBL_RESET, False)  # Soft Reset
            self.protoneer.send_gcode("$X", False)     # Enable
            self.protoneer.send_gcode("$$")            # Print Settings

            print("Homing Axes")
            self.protoneer.send_gcode("$H")  # Home all axes
            self.wait_for_idle()

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured while Homing Machine!")
            
        finally:
            if self.protoneer.is_connected():
                print("Putting GRBL to Sleep")
                self.protoneer.send_gcode("$SLP")  # Sleep GRBL
                if not was_connected:
                    print("Disconnecting GRBL")
                    self.protoneer.disconnect()

    def test_connection(self):
        print("Testing Connection")
        was_connected = self.protoneer.is_connected()
        try:
            if was_connected:
                self.protoneer.disconnect()
            self.protoneer.connect(sefl.settings['port'])
            yield True
        except Exception as ex:
            print()
            print(ex)
            print(f"Exception Raised while testing connection! {was_connected=}")
            yield False
        finally:
            if not was_connected and self.protoneer.is_connected():
                print("Disconnecting GRBL")
                self.protoneer.disconnect()

    def connect_and_sleep(self):
        print("Connecting and Putting GRBL to Sleep")
        was_connected = self.protoneer.is_connected()
        try:
            if not was_connected:
                self.protoneer.connect(sefl.settings['port'])
            print("Putting GRBL to Sleep")
            self.protoneer.send_gcode("$SLP")  # Sleep GRBL
            yield True
        except Exception as ex:
            print()
            print(ex)
            print(f"Exception Raised while trying to sleep! {was_connected=}")
            yield False
        finally:
            if not was_connected and self.protoneer.is_connected():
                print("Disconnecting GRBL")
                self.protoneer.disconnect()

    def wait_for_idle(self):
        print("Waiting for Idle")
        status = self.protoneer.send_gcode("?")
        while not any(["Idle" in e for e in status]):
            time.sleep(0.25)
            status = self.protoneer.send_gcode("?")
            print(status)

    def spin_tray(self, revolutions=1, direction=0):
        print(f"Spinning Tray {revolutions=} {direction=}")
        GPIO.output(self.TRAY_DIR_PIN, direction)  # 1 = CCW, 0 = CW
        for _ in range(int(self.TRAY_REV_DIST * revolutions)):
            GPIO.output(self.TRAY_STEP_PIN, GPIO.HIGH)
            time.sleep(.001)
            GPIO.output(self.TRAY_STEP_PIN, GPIO.LOW)
            time.sleep(.001)

    def do_load_tag_routine(self, err_on_cancel=True):
        print("Loading Tag")
        self.spin_tray(1, self.TRAY_CCW)
        resp = QMessageBox.question(self.window, 
            'Loading Tag', 
            'Did the tag load correctly?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if resp == QMessageBox.Cancel:
            if err_on_cancel:
                raise CancelRoutineExpcetion()
            else:
                return False
        elif resp == QMessageBox.No:
            do_load_tag_routine()
        else:
            return True

    def pulse_peener(self):
        print("Pulsing Peener")
        self.pwm.start(self.PEEN_HIGH)
        time.sleep(0.3)
        self.pwm.start(0)
        time.sleep(0.5)

    def pulse_peener_until_up(self, err_on_cancel=True):
        self.pulse_peener()
        resp = QMessageBox.question(self.window, 
            'Stopping Peener', 
            'Is the peener lifted off the tag?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if resp == QMessageBox.Cancel:
            if err_on_cancel:
                raise CancelRoutineExpcetion()
            else:
                return False
        elif resp == QMessageBox.No:
            pulse_peener_until_up()
        else:
            return True

    def dispense_tag(self):
        print("Dispensing Tag")
        self.spin_tray(0.25, self.TRAY_CCW)
        time.sleep(self.DWELL)
        self.spin_tray(0.25, self.TRAY_CW)
        time.sleep(self.DWELL)

    def do_engraving_routine(self, step=0):
        if len(self.canvas.get_paths()) < 1:
            print("Canvas needs at least 1 line.")
            QMessageBox.warning(self.window, 'Cannot Peen Design', 'Cannot peen design, canvas needs at least one line.')
            return
        if not self.settings['port']:
            print("Port not set.")  # TODO: Popup Dialog
            QMessageBox.warning(self.window, 'Cannot Peen Design', 'Port not set.')
            return

        confirm = QMessageBox.question(self.window, 
            'Peen Design', 
            'Are you sure you want to peen this design?',
            QMessageBox.No | QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        print("Initializing Peener")
        try:
            print("Connecting GRBL")
            self.protoneer.connect(self.settings['port'])

            print("Initializing GRBL")
            self.protoneer.send_gcode(self.GRBL_RESET, False)  # Soft Reset
            self.protoneer.send_gcode("$X")     # Enable
            self.protoneer.send_gcode("$$")     # Print Settings
            time.sleep(self.DWELL)

            print("Homing Axes")
            self.protoneer.send_gcode("$H")  # Home all axes
            self.wait_for_idle()

            self.protoneer.send_gcode([
                f"G92 X-{self.WORK_OFFSET[0]} Y-{self.WORK_OFFSET[1]}",  # Set Work origin
                "$1=255",  # Position Hold steppers when Idle
                "$X",  # Enable
            ])
            time.sleep(self.DWELL)

            print("Initializing Motion")
            self.protoneer.send_gcode([
                "G17",   # XY Plane
                "G21",   # mm mode
                "G53",   # Machine coords
                "G90"    # Absolute mode
                # "G0 Z1"  # Move clamp up a litte (really just to activate servos to let tray spin)
            ])
            time.sleep(self.DWELL)

            self.do_load_tag_routine()

            print("Clamping Tag")
            self.protoneer.send_gcode("G0 Z10.5")  # Lower Clamp
            self.wait_for_idle()

            print("Moving into position")
            self.protoneer.send_gcode([
                "G54",            # Work coords
                f"G0 X{self.ENTRY_POINT[0]} Y{self.ENTRY_POINT[0]}",  # Move toward tag diagonally
                f"Y{self.ENTRY_POINT[1]}"  # Move into tag area
            ])

            scale = self.settings['tag_diam']
            pt_to_gcode = lambda x, y: "G0 X" + str(round(path[0][0] * scale, 2)) + " Y" + str(round(path[0][1] * scale, 2))

            for i, path in enumerate(self.canvas.get_paths()):
                print(f"Starting Path #{i}")

                print("  Moving to path start")
                self.protoneer.send_gcode(pt_to_gcode(*path[0]))  # Move to first position
                self.wait_for_idle()

                print("  Setting Peener to high speed")
                self.pwm.start(self.PEEN_HIGH)  # Set Peener to peen speed
                time.sleep(self.DWELL)

                print("  Drawing Path")
                self.protoneer.send_gcode([
                    "G0 X" + str(round(pt[0] * scale, 2)) + " Y" + str(round(pt[1] * scale, 2))
                    for pt in path[1:]
                ])
                self.wait_for_idle()

                print("  Done, Setting Peener to low speed")
                self.pwm.start(self.PEEN_LOW)  # Set Peener to travel speed
                time.sleep(self.DWELL)

            print("Stopping Peener")
            self.pwm.start(0)  # Turn off Peener
            time.sleep(self.DWELL)

            print("Lifting Peener")
            self.pulse_peener_until_up()

            print("Parking Peener")
            self.protoneer.send_gcode([
                f"G0 X{self.ENTRY_POINT[0]} Y{self.ENTRY_POINT[1]}",  # Move back to entry point
                f"Y-{self.WORK_OFFSET[1] - self.WORK_OFFSET[0]}"  # Move out of clamp
            ])
            self.wait_for_idle()

            self.protoneer.send_gcode([
                f"G0 Z0",  # Open Clamp
                f"X-{self.WORK_OFFSET[0]} Y-{self.WORK_OFFSET[1]}"  # Move to home position
            ])
            time.sleep(2)
            # self.wait_for_idle()

            self.dispense_tag()

        except CancelRoutineExpcetion():
            print("Routine Cancelled by user!")

        except Exception as ex:
            print()
            print(ex)
            print("Exception Occured with Peening!")
            print("Stopping Peener (EX)")
            self.e_stop()
            QMessageBox.critical(self.window,
                "Error While Peening", 
                "An Error occured while Peening. Machine has been stopped for safety."
            )
            
        finally:
            print("Stopping Peener")
            self.pwm.start(0)
            print("Disconnecting GRBL")
            if self.protoneer.is_connected():
                self.protoneer.send_gcode([
                    "$1=0",  # Steppers off when Idle
                    "$SLP"  # Sleep GRBL
                ])
                if not was_connected:
                    self.protoneer.disconnect()

        print("Done")


class CancelRoutineExpcetion(Exception):
    def __init__(self):
        super(self).__init__()