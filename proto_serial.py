import serial
import time

import platform
IS_FAKE = any([e in platform.platform().lower() for e in ["macos", "windows"]])

DEBUG_PRINT = True

class ProtoSerial:
    INIT_STR = "\r\n\r\n"

    def __init__(self):
        if not IS_FAKE:
            self.ser = serial.Serial()
            self.ser.baudrate = 115200
        else:
            self._connected = True

    def connect(self, port):
        if IS_FAKE:
            self._connected = True
            return
        if self.ser.is_open:
            self.ser.close()
        self.ser.port = port
        self.ser.open()

        self.send(self.INIT_STR, False)
        time.sleep(2)
        self.ser.flushInput()

    def disconnect(self):
        if IS_FAKE:
            self._connected = False
            return
        if self.ser.is_open:
            self.ser.close()

    def is_connected(self):
        if IS_FAKE:
            return self._connected
        return self.ser.is_open

    def send(self, gcode, wait_for_resp=True):
        if type(gcode) is str:
            gcode = [gcode]

        if IS_FAKE:
            if DEBUG_PRINT:
                print(f"Send: {gcode}")
            if any(["$H" in e for e in gcode]):
                time.sleep(5)
            elif any(["G0" in e for e in gcode]):
                time.sleep(0.1)
            return ["Idle"]

        resps = []
        if self.ser.is_open:
            # Stream g-code to grbl
            for line in gcode:
                l = line.strip()
                if not line:
                    continue
                if DEBUG_PRINT:
                    print(f'Sending: {self._escape_str(line)}')
                self.ser.write((f'{l}\n').encode())
                time.sleep(0.05)
                # if wait_for_resp:
                for _ in range(5):
                    time.sleep(0.01)
                    if self.ser.in_waiting:
                        break
                    # while not self.ser.in_waiting:
                    #     time.sleep(0.1)
                while self.ser.in_waiting:
                    resps += [self.ser.readline().decode().strip()]
                    if DEBUG_PRINT:
                        print(f'  Recv: {self._escape_str(resps[-1])}')
            return resps
        return False

    def _escape_str(self, string):
        return string.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')