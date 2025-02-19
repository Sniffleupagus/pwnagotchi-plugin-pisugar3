# Based on UPS Lite v1.1 from https://github.com/xenDE

import logging
import struct
import time

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi

class UPS:
    def __init__(self, i2c_bus=1):
        # only import when the module is loaded and enabled
        import smbus
        # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        self._bus = smbus.SMBus(i2c_bus)

    def busReadMultiTry(self, addr, idx, tries = 3):
        val = None
        while tries > 0:
            tries -= 1
            try:
                val = self._bus.read_byte_data(addr, idx)
                return val
            except Exception as e:
                if tries > 0:
                    logging.debug("Retry %d: %s" % (tries, repr(e)))
                else:
                    logging.error("Retries failed: %s" % repr(e))
        return val

    def voltage(self):
        i = 3
        low = None
        high = None
        while i > 0:
            try:
                if low == None: low = self.busReadMultiTry(0x57, 0x23)
                if high == None: high = self.busReadMultiTry(0x57, 0x22)
                v = (((high << 8) + low)/1000)
                i = 0
            except Exception as e:
                logging.error(e)
                v = 69
                i = i - 1
                time.sleep(0.5)
        return v

    def capacity(self):
        battery_level = 420
        # battery_v = self.voltage()
        i = 3
        while i > 0:
            try:
                battery_level = self.busReadMultiTry(0x57, 0x2a)
                return battery_level
            except Exception as e:
                logging.error(e)
                i = i - 1
                time.sleep(0.5)
        return battery_level


    def status(self):
        i = 3
        stat02 = None
        stat03 = None
        stat04 = None
        while i > 0:
            try:
                if stat02 == None: stat02 = self.busReadMultiTry(0x57, 0x02)
                if stat03 == None: stat03 = self.busReadMultiTry(0x57, 0x03)
                if stat04 == None: stat04 = self.busReadMultiTry(0x57, 0x04)
                i = 0
            except Exception as e:
                logging.error("Try again %s" % repr(e))
                i = i - 1
                time.sleep(0.5)

        return stat02, stat03, stat04

class PiSugar3(plugins.Plugin):
    __author__ = 'taiyonemo@protonmail.com'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin that will add a percentage indicator for the PiSugar 3'

    def __init__(self):
        self.ups = None
        self._ready = False
        self.lasttemp = 69
        self.drot = 0 # display rotation
        self.nextDChg = 0 # last time display changed, rotate on updates after 5 seconds

    def on_loaded(self):
        self.ups = UPS(i2c_bus=self.options.get("i2c_bus", 1))
        logging.info("[pisugar3] plugin loaded.")

    def on_ui_setup(self, ui):
        try:
            ui.add_element('bat', LabeledValue(color=BLACK, label='BAT', value='0%', position=(ui.width() / 2 + 10, 0),
                                               label_font=fonts.Bold, text_font=fonts.Medium))
            self._ready = True
        except Exception as err:
            logging.warning("pisugar3 setup err: %s" % repr(err))

    def on_unload(self, ui):
        try:
            with ui._lock:
                ui.remove_element('bat')
        except Exception as err:
            logging.warning("pisugar3 unload err: %s" % repr(err))

    def on_ui_update(self, ui):
        if not self._ready:
          return

        capacity = self.ups.capacity()
        voltage = self.ups.voltage()
        stats = self.ups.status()
        temp = stats[2] - 40
        if temp != self.lasttemp:
            logging.debug("pisugar3 (chg %X, info %X, temp %d)" % (stats[0], stats[1], temp))
            self.lasttemp = temp

        if stats[0] & 0x80: # charging, or has power connected
            ui._state._state['bat'].label = "CHG"
        else:
            ui._state._state['bat'].label = "BAT"

            
        if time.time() > self.nextDChg:
            self.drot = (self.drot + 1) % 3
            self.nextDChg = time.time() + 5

        if self.drot == 0:  # show battery voltage
            ui.set('bat', "%2.2fv" % (voltage))
        elif self.drot == 1:
            ui.set('bat', "%2i%%" % (capacity))
        else:
            ui.set('bat', "%2i\xb0" % (temp));
                
        if capacity <= self.options.get('shutdown', -1):
            logging.info('[pisugar3] Empty battery (<= %s%%): shuting down' % self.options['shutdown'])
            ui.update(force=True, new_data={'status': 'Battery exhausted, bye ...'})
            pwnagotchi.shutdown()
