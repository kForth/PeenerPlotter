BCM = "BCM"
BOARD = "BOARD"
IN = "IN"
OUT = "OUT"
HIGH = "HIGH"
LOW = "LOW"

def setmode(*args, **kwargs):
    print(f"GPIO.setMode args=({args}) kwargs=(kwargs)")

def setup(*args, **kwargs):
    print(f"GPIO.setup args=({args}) kwargs=(kwargs)")

def output(*args, **kwargs):
    # print(f"GPIO.output args=({args}) kwargs=(kwargs)")
    pass

def input(*args, **kwargs):
    # print(f"GPIO.input args=({args}) kwargs=(kwargs)")
    return 1

def PWM(*args, **kwargs):
    print(f"GPIO.PWM args=({args}) kwargs=(kwargs)")
    return fake_pwm()

class fake_pwm:
    def start(self, *args, **kwargs):
        print(f"PWM.start args=({args}) kwargs=(kwargs)")

    def stop(self, *args, **kwargs):
        print(f"PWM.stop args=({args}) kwargs=(kwargs)")