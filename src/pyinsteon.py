'''
File:
		pyinsteon.py

Description:
		Insteon Home Automation Protocol library for Python (Smarthome 2412N, 2412S, 2412U)
		
		For more information regarding the technical details of the PLM:
				http://www.smarthome.com/manuals/2412sdevguide.pdf

Author(s): 
		 Jason Sharpee <jason@sharpee.com>	http://www.sharpee.com
		 mahmul @ #python
		 Ene Uran 01/19/2008	http://www.daniweb.com/software-development/python/code/217019

		Based loosely on the Insteon_PLM.pm code:
		-		Expanded by Gregg Liming <gregg@limings.net>

License:
	This free software is licensed under the terms of the GNU public license, Version 1		

Usage:
	- Instantiate PyInsteon by passing in an interface
	- Call its methods
	- ?
	- Profit

Example: (see bottom of file) 

	def x10_received(houseCode, unitCode, commandCode):
		print 'X10 Received: %s%s->%s' % (houseCode, unitCode, commandCode)

	def insteon_received(*params):
		print 'Insteon REceived:', params

	pyI = PyInsteon(TCP('192.168.0.1', 9671))
	pyI.getVersion()
	pyI.sendX10('m', '2', 'on')
	pyI.onReceivedX10(x10_received)
	pyI.onReceivedInsteon(insteon_received)
	select.select([],[],[])	  

Notes:
	- Only support 2412N right now
	- Insteon is not quite finished / untested
	- Read Style Guide @: http://www.python.org/dev/peps/pep-0008/

Created on Mar 26, 2011
'''
import socket
import threading
import binascii
import select
import time
import pprint

import utilities
import pyftdi


HOST='192.168.13.146'
PORT=9761

class Lookup(dict):
	"""
	a dictionary which can lookup value by key, or keys by value
	# tested with Python25 by Ene Uran 01/19/2008	 http://www.daniweb.com/software-development/python/code/217019
	"""
	def __init__(self, items=[]):
		"""items can be a list of pair_lists or a dictionary"""
		dict.__init__(self, items)
	def get_key(self, value):
		"""find the key as a list given a value"""
		items = [item[0] for item in self.items() if item[1] == value]
		return items[0]	  
	 
	def get_keys(self, value):
		"""find the key(s) as a list given a value"""
		return [item[0] for item in self.items() if item[1] == value]
	def get_value(self, key):
		"""find the value given a key"""
		return self[key]

#PLM Serial Commands
keys = ('insteon_received',
		'insteon_ext_received',
		'x10_received',
		'all_link_complete',
		'plm_button_event',
		'user_user_reset',
		'all_link_clean_failed',
		'all_link_record',
		'all_link_clean_status',
		'',
		'',
		'',
		'',
		'',
		'',
		'',
		'plm_info',
		'all_link_send',
		'insteon_send',
		'x10_send',
		'all_link_start',
		'all_link_cancel',
		'plm_reset',
		'all_link_first_rec',
		'all_link_next_rec',
		'plm_set_config',
		'plm_led_on',
		'plm_led_off',
		'all_link_manage_rec',
		'insteon_nak',
		'insteon_ack',
		'rf_sleep',
		'plm_get_config')

PLM_Commands = Lookup(zip(keys,xrange(0x250, 0x273)))
#pprint.pprint(commands)

Insteon_Commmand_Codes = Lookup({
								 'on':0x11,
								 'fast_on':0x12,
								 'off':0x19,
								 'fast_off':0x20
								 })
	
### Possibly error in Insteon Documentation regarding command mapping of preset dim and off
keys = (
		'all_lights_off',
		'status_off',
		'on',
#		 'preset_dim',
		'off',
		'all_lights_on',
		'hail_acknowledge',
		'bright',
		'status_on',
		'extended_code',
		'status_request',
#		 'off',
		'present_dim'
		'preset_dim2',
		'all_units_off',
		'hail_request',
		'dim',
		'extended_data'
		)
X10_Command_Codes = Lookup(zip(keys,xrange(0,15)))

X10_Types = Lookup({
					'unit_code': 0x0, 
					'command_code': 0x80
					})

keys = ( 'm',
		 'e',
		 'c',
		 'k',
		 'o',
		 'g',
		 'a',
		 'i',
		 'n',
		 'f',
		 'd',
		 'l',
		 'p',
		 'h',
		 'n',
		 'j' )

X10_House_Codes = Lookup(zip(keys,xrange(0x0, 0xF)))
		
keys = (
		'13',
		'5',
		'3',
		'11',
		'15',
		'7',
		'1',
		'9',
		'14',
		'6',
		'4',
		'12',
		'16',
		'8',
		'2',
		'10'
		)
X10_Unit_Codes = Lookup(zip(keys,xrange(0x0,0xF)))

class Interface(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)

		self._shutdownEvent = threading.Event()
		self._interfaceRunningEvent = threading.Event()

	def shutdown(self):
		self._shutdownEvent.set()

		#wait 2 seconds for the interface to shut down
		self._interfaceRunningEvent.wait(2000)
		
	def _send(self,Data):
		return None

	def onReceive(self, callback):
		self.c = callback
		return None	   
   
class TCP(Interface):
	def __init__(self):
		super(TCP, self).__init__(host,port)		
		self.__s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		print"connect"
		self.__s.connect((host, port))
		self.start()

		
	def send(self, dataString):
		"Send raw HEX encoded String"
		print "Data Sent=>" + dataString
		data = binascii.unhexlify(dataString)
		self.__s.send(data) 
		return None
	
	def run(self):
		self._handle_receive()
		

		
	def _handle_receive(self):
		while 1:
			data = self.__s.recv(1024)
			self.c(data)
		self.__s.close()
		
class Serial(Interface):
	def __init__(self, port, speed):
		return None
	pass
	
class USB(Interface): 
	pass
	def __init__(self, device):
		return None

class FTDI(Interface):
	def __init__(self, deviceSerialNumber):
		super(FTDI, self).__init__()		

		self.__ftdiDevice = pyftdi.pyftdi()

		print "Opening FTDI Device: " + deviceSerialNumber
		self.__ftdiDevice.open(serialNumber = deviceSerialNumber)
		self.__ftdiDevice.set_baudrate(19200)
		self.__ftdiDevice.usb_read_timeout = 1000

	def send(self,dataString):
		try:
			data = binascii.unhexlify(dataString)
			print "Sending: "
			print utilities.hex_dump(data, len(data))

			self.__ftdiDevice.write_data(data)
		except:
			pass

	def run(self):
		self._interfaceRunningEvent.set();

		while not self._shutdownEvent.isSet():
			try:
				readBytes = self.__ftdiDevice.read_data(1024)
				if len(readBytes) > 0:
					print "Received: "
					print utilities.hex_dump(readBytes, len(readBytes))

					self.c(readBytes)
				else:
					time.sleep(0.5)

			except Exception, ex:
				print ex
				pass

		self._interfaceRunningEvent.clear()
	
class HAProtocol(object):
	"Base protocol interface"
	def __init__(self, interface):
		pass
	
class PyInsteon(HAProtocol):
	"The Main event"
	
	def __init__(self, interface):
		super(PyInsteon, self).__init__(interface)		  
		self.__i = interface
		self.__i.onReceive(self._handle_received)
		self.__dataReceived = threading.Event()
		self.__dataReceived.clear()
		self.__callback_x10 = None
		self.__callback_insteon = None
		self.__x10UnitCode = None
		
		#PLM info property holders
		self.__PLMInfoFetched = False
		self.__PLMInfo = dict(id = None, devCat = None, devSubCat = None, firmwareVersion = None)
		
		#start up the interface's thread to deal with reception
		self.__i.start()
		return None
		
	def shutdown(self):
		#ensure that the interface is shutdown before we shut down everything
		self.__i.shutdown()

	def _handle_received(self,data):
		dataHex = binascii.hexlify(data)
		print "Data Received=>" + dataHex
		plm_command = int(dataHex[0:4],16)
		print "Command->%d %s '%s'" % (plm_command,plm_command,PLM_Commands.get_key(plm_command))
		callback = { 
						'plm_info': self._recvPLMInfo,
						'insteon_received': self._recvInsteon,
						'insteon_ext_received': self._recvInsteon,
						'x10_received': self._recvX10
					}.get(PLM_Commands.get_key(plm_command))
		if callback:
			callback(dataHex)

		#Let other threads know data has been received and processed
		self.__dataReceived.set()

	def _recvPLMInfo(self,dataHex):
		"Receive Handler for PLM Info"		
		#R: 0x02 0x60 <ID high byte> <ID middle byte> <ID low byte> <Device Category> <Device Subcategory> < Firmware Revision> <0x06>
		self.__PLMInfo['id'] = dataHex[4:10]
		self.__PLMInfo['devCat'] = dataHex[11:12]
		self.__PLMInfo['devSubCat'] = dataHex[13:14]
		self.__PLMInfo['firmwareVersion']=dataHex[14:16]
		
		self.__PLMInfoFetched = True
		
	def getPLMInfo(self):
		if self.__PLMInfoFetched == False:
			self._send("%04x" %PLM_Commands['plm_info'])
			self.__dataReceived.wait(1000)

		return self.__PLMInfo

	def _recvInsteon(self,dataHex):
		"Receive Handler for Insteon Data"
		group=None
		userData=None

		fromAddress =		dataHex[4:6] + "." + dataHex[6:8] + "." +  dataHex[8:10] 
		toAddress =			dataHex[10:12] + "." + dataHex[12:14] + "." +  dataHex[14:16]
		messageDirect =		((int(dataHex[16:18],16) & 0b11100000) >> 5)==0
		messageAcknowledge =((int(dataHex[16:18],16) & 0b00100000) >> 5)>0
		messageGroup =		((int(dataHex[16:18],16) & 0b01000000) >> 6)>0
		if messageGroup:
			group =				dataHex[14:16] # overlapped into toAddress if a group call is made
		messageBroadcast =	((int(dataHex[16:18],16) & 0b10000000) >> 7)>0
		extended =			((int(dataHex[16:18],16) & 0b00010000) >> 4)>0 #4th MSB
		hopsLeft =			(int(dataHex[16:18],16) & 0b00001100) >> 2 #3-2nd MSB
		hopsMax =			(int(dataHex[16:18],16) & 0b00000011)  #0-1 MSB
		# could have also used ord(binascii.unhexlify(dataHex[16:17])) & 0b11100000
		command1=		dataHex[18:20]
		command2=		dataHex[20:22]
		if extended:
			userData =		dataHex[22:36]
		
		#print "Insteon=>From=>%s To=>%s Group=> %s MessageD=>%s MB=>%s MG=>%s MA=>%s Extended=>%s HopsLeft=>%s HopsMax=>%s Command1=>%s Command2=>%s UD=>%s" % \
		#	(fromAddress, toAddress, group, messageDirect, messageBroadcast, messageGroup, messageAcknowledge, extended, hopsLeft, hopsMax, command1, command2, userData)
		if self.__callback_insteon != None:
			self.__callback_insteon(fromAddress, toAddress, group, messageDirect, messageBroadcast, messageGroup, messageAcknowledge, extended, hopsLeft, hopsMax, command1, command2, userData)
	
	def _recvX10(self,dataHex):
		"Receive Handler for X10 Data"
		#X10 sends commands fully in two separate messages"
		unitCode = None
		commandCode = None
		houseCode =		(int(dataHex[4:6],16) & 0b11110000) >> 4 
		houseCodeDec = X10_House_Codes.get_key(houseCode)
		keyCode =		(int(dataHex[4:6],16) & 0b00001111)
		flag =			int(dataHex[6:8],16)
#		 print "X10=>House=>%s Unit=>%s Command=>%s Flag=%s" % (houseCode, unitCode, commandCode, flag)
		if flag == X10_Types['unit_code']:
			unitCode = keyCode
			unitCodeDec = X10_Unit_Codes.get_key(unitCode)
			#print "X10: Beginning transmission X10=>House=>%s Unit=>%s" % (houseCodeDec, unitCodeDec)
			self.__x10UnitCode = unitCodeDec
		elif flag == X10_Types['command_code']:
			commandCode = keyCode
			commandCodeDec = X10_Command_Codes.get_key(commandCode)
			#print "Fully formed X10=>House=>%s Unit=>%s Command=>%s" % (houseCodeDec, self.__x10UnitCode, commandCodeDec)
			#Only send fully formed messages
			if self.__callback_x10 != None:
				self.__callback_x10(houseCodeDec, self.__x10UnitCode, commandCodeDec)
			self.__x10UnitCode = None

	def _send(self,dataHex):
		"Send raw data"
		#We are starting a new transmission, clear any blocks on receive
		self.__dataReceived.clear()
		self.__i.send(dataHex)
		#Slow down the interface when sending.	Takes a while and can overrun easily
		#todo make this adaptable based on Ack / Nak rates
		# Of interest is that the controller will return an Ack before it is finished sending, so overrun wont be seen until next send
		time.sleep(.5)

	def sendInsteon(self, fromAddress, toAddress, group, messageDirect, messageBroadcast, messageGroup, messageAcknowledge, extended, hopsLeft, hopsMax, command1, command2, data):
		"Send raw Insteon message"
		messageType=0
		if extended==False:
			dataString	= "%04x" % PLM_Commands['insteon_send']
		else:
			dataString = "%04x" % PLM_Commands['insteon_ext_send']
		dataString += fromAddress[0:2] + fromAddress[3:5] + fromAddress[6:7]
		dataString += toAddress[0:2] + toAddress[3:5] + toAddress[6:7]
		if messageAcknowledge:
			messageType=messageType | 0b00100000
		if messageGroup:
			messageType=messageType | 0b01000000
		if messageBroadcast:
			messageType=messageType | 0b10000000
		#Message Direct clears all other bits.. sorry thats the way it works
		if messageDirect:
			messageType=0
		if extended:
			messageType=messageType | 0b00010000
		messageType = messageType | (hopsLeft  << 2)
		messageType = messageType | hopsMax
		dataString += binascii.hexlify(messageType)
		dataString += command1
		dataString += command2
		if extended:
			dataString += data

		#crc goes here?

		print "InsteonSend=>%s" % (dataString)
		self._send(dataString)
		
	def sendX10(self, houseCode, unitCode, commandCode):
		"Send Fully formed X10 Unit / Command"
		self.sendX10Unit(houseCode, unitCode)

		#wait for acknowledge.
		self.__dataReceived.wait(1000)
				
		self.sendX10Command(houseCode, commandCode)

	def sendX10Unit(self,houseCode,unitCode):
		"Send just an X10 unit code message"
		
		houseCode=houseCode.lower()
		unitCodeEnc = X10_Unit_Codes[unitCode]
		houseCodeEnc = X10_House_Codes[houseCode]
		dataString = "%04x" % PLM_Commands['x10_send']
		firstByte = houseCodeEnc << 4
		firstByte = firstByte | unitCodeEnc
		dataString+= "%02x" % (firstByte)
		dataString+=  "%02x" % X10_Types['unit_code']
		self._send(dataString)

	def sendX10Command(self,houseCode,commandCode):
		"Send just an X10 command code message"

		houseCode=houseCode.lower()
		commandCode = commandCode.lower()
		commandCodeEnc= X10_Command_Codes[commandCode]
		houseCodeEnc = X10_House_Codes[houseCode]
		dataString = "%04x" % PLM_Commands['x10_send']
		firstByte = houseCodeEnc << 4
		firstByte = firstByte | commandCodeEnc
		dataString+= "%02x" % (firstByte)
		dataString+= "%02x" % X10_Types['command_code']
		self._send(dataString)
		
	def onReceivedX10(self, callback):
		"Set callback for reception of an X10 message"
		self.__callback_x10=callback
		return
	
	def onReceivedInsteon(self, callback):
		"Set callback for reception of an Insteon message"
		self.__callback_insteon=callback
		return

######################
# EXAMPLE			 #
######################

def x10_received(houseCode, unitCode, commandCode):
	print 'X10 Received: %s%s->%s' % (houseCode, unitCode, commandCode)

def insteon_received(*params):
	print 'Insteon Received:', params
	
if __name__ == "__main__":
	pyI = PyInsteon(TCP(HOST, PORT))
	pyI.onReceivedX10(x10_received)
	pyI.onReceivedInsteon(insteon_received)
	pyI.getVersion()
	pyI.sendX10('m', '2', 'on')
	pyI.sendX10('m', '1', 'on')
	pyI.sendX10('m', '1', 'off')
	select.select([],[],[])
	
