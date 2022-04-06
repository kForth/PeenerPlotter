from PyQt5 import uic
from PyQt5.QtWidgets import QDialog

from serial_ports import serial_ports

class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi('settings_dialog.ui', self)
        # self.setFixedSize(self.size())

        ports = serial_ports()
        self.port_comboBox.clear()
        for port in ports:
            self.port_comboBox.addItem(port)
        
        self.show()

    def get_settings(self):
        return {
            "port": ""
        }