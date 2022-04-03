import serial
import time

class Engraver:
    INIT_STR = "\r\n\r\n"

    def __init__(self):
        self.ser = serial.Serial()
        self.ser.baudrate = 115200

    def connect(self, port):
        if self.ser.is_open:
            self.ser.close()
        self.ser.port = port
        self.ser.open()

        self.send_gcode(self.INIT_STR, False)
        time.sleep(2)
        self.ser.flushInput()

    def disconnect(self):
        if self.ser.is_open:
            self.ser.close()

    def is_connected(self):
        return self.ser.is_open

    def send_gcode(self, gcode, wait_for_resp=True):
        if type(gcode) is str:
            gcode = [gcode]
        resps = []
        if self.ser.is_open:
            # Stream g-code to grbl
            for line in gcode:
                l = line.strip()
                if line:
                    print(f'Sending: {self._escape_str(line)}')
                    self.ser.write((f'{l}\n').encode())
                    if wait_for_resp:
                        resp = self.ser.readline().decode().strip()
                        print(f'  Recv: {self._escape_str(resp)}')
                        resps += [resp]
            return resps
        return False

    def _escape_str(self, string):
        return string.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')