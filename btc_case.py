#!/usr/bin/python
 
import urllib2
import json
import serial
import sys
import threading
import time
import ctypes
import signal
import logging
import argparse
import qrcode
import piper as Piper

from subprocess import *
from select import error as select_error
from time import sleep, strftime
from datetime import datetime
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

sys.path.append('/home/pi/build/Python-Thermal-Printer')
from Adafruit_Thermal import *

log = logging.getLogger(__name__)
 
exit_now = False
 
def signal_handler(signal, frame):
	log.debug('Got SIGINT, quitting.')
	global exit_now
	exit_now = True
 
 
def get_cur_exchange_rate():
	try:
		resp = urllib2.urlopen('https://data.mtgox.com/api/2/BTCUSD/money/ticker_fast')
	except urllib2.URLError as e:
		log.warn('Unable to fetch exchange rate: %s' % e)
		return None, None
 
	try:
		exch_data = json.load(resp)
	except ValueError as e:
		log.warn('Unable to parse data from exchange site: %s', e)
		return None, None
 
	if 'data' in exch_data and 'last' in exch_data['data'] and 'value' in exch_data['data']['last']:
		btc = exch_data['data']['last']['value']
		return float(btc), 1.0/float(btc)
 
	# error
	log.warn('Got unparsable data from Bitcoin site')
	return None, None
 
 
class fake_lcd(object):
	''' used to test Display functionality by printing to stdout.
	can be removed or put in another file later.'''
	def __init__(self):
		pass
 
	def begin(self, x, y):
		print '-- lcd begin --'
 
	def clear(self):
		print '--clear--'
 
	def setCursor(self, x, y):
		pass
 
	def message(self, m):
		print m
 
 
class fake_arduino(object):
	def __init__(self):
		pass
 
	def close(self):
		pass
 
	def readline(self):
		return "foobar"
 
 
def lcd_display(lcd, s1, s2):
	lcd.clear()
	lcd.setCursor(0,0)
	lcd.message(s1)
	lcd.setCursor(0,1)
	lcd.message(s2)
 
 
def display_exch_rate(lcd, btc, usd, alt_line='Insert Coins!'):
	s1 = alt_line if not btc else '1BTC=$'+"{:.2f}".format(btc)
	s2 = alt_line if not usd else '1USD=B'+"{:.7f}".format(usd)
	lcd_display(lcd, s1, s2)
 
 
class DisplayClass(threading.Thread):
	def __init__(self):
		super(DisplayClass, self).__init__()
		self._stop = False
		self._paused = False
 
	def stop(self):
		self._stop = True
 
	def pause(self):
		self._paused = True

	def resume(self):
		self._paused = False
 
	def run(self):
		while not self._stop:
			if self._paused:
				# log message here?
				time.sleep(1)
				continue
 
			btc, usd = get_cur_exchange_rate()
			if not btc:
				time.sleep(2)
				continue
 
			# a little hacky
			for b, u in [(btc, usd), (None, usd), (btc, usd), (btc, None)]:
				display_exch_rate(lcd, b, u)
				time.sleep(2)
				if self._paused or self._stop:
					break
 
#
# main()
#
if __name__ == "__main__":
	signal.signal(signal.SIGINT, signal_handler)
 
	parser = argparse.ArgumentParser(description='Handle bitcoin interactions.')
	parser.add_argument('-d', '--debug', dest='debug', default=False,
						action='store_true', help='Enable debugging '
						'functionality and logging.')
	args = parser.parse_args()
 
	if args.debug:
		lcd = fake_lcd()
		arduino = fake_arduino()
		logging.basicConfig(level=logging.DEBUG)
	else:
		sys.path.append('/home/pi/build/Adafruit_CharLCD')
		from Adafruit_CharLCD import Adafruit_CharOLED
		import RPi.GPIO as GPIO
		 
		lcd = Adafruit_CharOLED()
		arduino = serial.Serial('/dev/ttyACM0', 115200)
		logging.basicConfig(level=logging.CRITICAL)
 
	lcd.begin(16,2)
 
	d = DisplayClass()
	d.start()
 
	while not exit_now:
		try:
			input = arduino.readline().strip()
		except select_error:
			break
		command = str(input[:1])
		input = input[1:]
 
		if command == "+":
			d.pause()
			input = float(input) / 100
			btc, usd = get_cur_exchange_rate()
			if not btc:
				time.sleep(2)
				continue

			lcd_display(lcd, "$"+"{:.2f}".format(input)+" Inserted",
						'1USD=B'+"{:.7f}".format(usd))
 
		if command == ">":
			d.pause()
			input = float(input) / 100
			returnAmt = usd*input
			lcd_display(lcd, "$"+"{:.2f}".format(input)+" Inserted", 'Return '"{:.5f}".format(returnAmt))
			time.sleep(2)
			
			pubkey = Piper.genAndPrintKeys(btc, input, 1, "", lcd)
			lcd_display(lcd, 'DOEN! ^_^', ' ')
			print pubkey
			time.sleep(2)
			d.resume()            
			
	print "Stopping"
	d.stop()
	d.join()
	lcd.clear()
	if not args.debug:
		GPIO.cleanup()
	arduino.close()
	sys.exit(0)


