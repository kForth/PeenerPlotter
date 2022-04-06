import serial
import time

import platform
IS_FAKE = "macos" in platform.platform().lower()

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

        self.send_gcode(self.INIT_STR, False)
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

    def send_gcode(self, gcode, wait_for_resp=True):
        if type(gcode) is str:
            gcode = [gcode]
        if IS_FAKE:
            print(f"Send: {gcode}")
            if any(["$H" in e for e in gcode]):
                time.sleep(10)
            return ["Idle"]
        resps = []
        if self.ser.is_open:
            # Stream g-code to grbl
            for line in gcode:
                l = line.strip()
                if line:
                    print(f'Sending: {self._escape_str(line)}')
                    self.ser.write((f'{l}\n').encode())
                    if wait_for_resp:
                        while not self.ser.in_waiting:
                            time.sleep(0.1)
                        while self.ser.in_waiting:
                            resp = self.ser.readline().decode().strip()
                            print(f'  Recv: {self._escape_str(resp)}')
                            resps += [resp]
            return resps
        return False

    def _escape_str(self, string):
        return string.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')