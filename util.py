import sys
import glob
import serial
import colorsys
import functools
from random import randint, shuffle

def serial_ports():
    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system

        https://stackoverflow.com/a/14224477
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result


def gen_colours(n, randomize=False, skip_wraparound=True, skip_yellow=True):
    """
        Generates n distinct colors.

        https://gist.github.com/kForth/ce52533f640ed031a7819bbc8bd35037
    """
    colours = []
    for i in range(n):
        hue = i / min(n - 1, 1)
        lum = 0.5 + randint(0, 10) / 100
        sat = 0.5 + randint(0, 10) / 100

        # Skip the Red wraparound
        if skip_wraparound:
            hue *= (160/180)

        # Skip Yellow and Light Green
        if skip_yellow:
            lb = 20/180
            ub = 40/180
            hue *= 1 - (lb - ub)
            if hue > lb:
                hue = hue + (lb - ub)
            
        colours.append(list(colorsys.hls_to_rgb(hue, lum, sat)))

    if randomize:
        shuffle(colours)
    return colours

def debug_func(func):
    """Print the function signature and return value"""
    @functools.wraps(func)
    def wrapper_debug(*args, **kwargs):
        args_repr = [repr(a) for a in args]                      # 1
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]  # 2
        signature = ", ".join(args_repr + kwargs_repr)           # 3
        print(f"Calling {func.__name__}({signature})")
        value = func(*args, **kwargs)
        print(f"{func.__name__!r} returned {value!r}")           # 4
        return value
    return wrapper_debug

if __name__ == "__main__":
    print(serial_ports())