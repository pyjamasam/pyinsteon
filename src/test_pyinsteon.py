'''
Created on Mar 26, 2011

@author: jason@sharpee.com
'''
import select
import traceback
import threading
import time
import binascii
import struct
import hashlib
from collections import deque

import utilities
import pyftdi

def _byteIdToStringId(idHigh, idMid, idLow):
	return '%02X.%02X.%02X' % (idHigh, idMid, idLow)
	
def _cleanStringId(stringId):
	return stringId[0:2] + stringId[3:5] + stringId[6:8]

def _stringIdToByteIds(stringId):
	return binascii.unhexlify(_cleanStringId(stringId))
	
def _buildFlags():
	#todo: impliment this
	return '\x0f'

class CWInsteon(threading.Thread):
	
	def __init__(self, deviceSerialNumber):
		super(CWInsteon, self).__init__()
		
		self.__modemCommands = {'60': {
									'responseSize':7,
									'callBack':self.__process_PLMInfo
								  },
								'62': {
									'responseSize':7,
									'callBack':self.__process_StandardInsteonMessagePLMEcho
								  },
								  
								'50': {
									'responseSize':9,
									'callBack':self.__process_InboundStandardInsteonMessage
								  },								
							}
		
		self.__insteonCommands = {
									'SD03': {		#Product Data REquest							
										'callBack' : self.__handle_StandardDirect_IgnoreAck
									},
									'SD0D': {		#Get Insteon Engine							
										'callBack' : self.__handle_StandardDirect_EngineResponse
									},
									'SD0F': {		#Ping Device						
										'callBack' : self.__handle_StandardDirect_PingResponse
									},
								  	'SD10': {		#ID Request							
										'callBack' : self.__handle_StandardDirect_IDRequest
									},	
									'SD11': {		#Devce On								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand
									},									
									'SD12': {		#Devce On Fast								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand
									},									
									'SD13': {		#Devce Off								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand
									},									
									'SD14': {		#Devce Off Fast								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand
									},									
									'SB01': {									
										'callBack' : self.__handle_StandardBroadcast_SetButtonPressed
									},								   
								}
		
		
		self._allLinkDatabase = dict()
		
		self.__shutdownEvent = threading.Event()
		self.__interfaceRunningEvent = threading.Event()
		
		self.__commandLock = threading.Lock()
		self.__outboundQueue = deque()
		self.__outboundCommandDetails = dict()			
		
		self.__pendingCommandDetails = dict()		
		
		self.__commandReturnData = dict()
								
		self.__ftdiDevice = pyftdi.pyftdi()

		print "Opening FTDI Device: " + deviceSerialNumber
		self.__ftdiDevice.open(serialNumber = deviceSerialNumber)
		self.__ftdiDevice.set_baudrate(19200)
		self.__ftdiDevice.usb_read_timeout = 1000
	
	def shutdown(self):
		if self.__interfaceRunningEvent.isSet():
			self.__shutdownEvent.set()

			#wait 2 seconds for the interface to shut down
			self.__interfaceRunningEvent.wait(2000)
			
	def run(self):
		self.__interfaceRunningEvent.set();

		while not self.__shutdownEvent.isSet():
			
			#check to see if there are any outbound messages to deal with
			self.__commandLock.acquire()
			if len(self.__outboundQueue) > 0:
				commandHash = self.__outboundQueue.popleft()
				
				commandExecutionDetails = self.__outboundCommandDetails[commandHash]
				
				bytesToSend = commandExecutionDetails['bytesToSend']
				print "Sending:"
				print utilities.hex_dump(bytesToSend, len(bytesToSend)),

				self.__ftdiDevice.write_data(bytesToSend)					
				
				self.__pendingCommandDetails[commandHash] = commandExecutionDetails				
				del self.__outboundCommandDetails[commandHash]
								
			self.__commandLock.release()	
			
			#check to see if there is anyting we need to read			
			firstByte = self.__ftdiDevice.read_data(1)
			if len(firstByte) == 1:
				#got at least one byte.  Check to see what kind of byte it is (helps us sort out how many bytes we need to read now)
									
				if firstByte[0] == '\x02':
					#modem command (could be an echo or a response)
					#read another byte to sort that out
					secondByte = self.__ftdiDevice.read_data(1)
										
					responseSize = -1
					callBack = None
					
					modemCommand = binascii.hexlify(secondByte).upper()
					if self.__modemCommands.has_key(modemCommand):
						if self.__modemCommands[modemCommand].has_key('responseSize'):																	
							responseSize = self.__modemCommands[modemCommand]['responseSize']							
						if self.__modemCommands[modemCommand].has_key('callBack'):																	
							callBack = self.__modemCommands[modemCommand]['callBack']							
							
					if responseSize != -1:						
						remainingBytes = self.__ftdiDevice.read_data(responseSize)
						
						print "Received: "
						print utilities.hex_dump(firstByte + secondByte + remainingBytes, len(firstByte + secondByte + remainingBytes))
						
						if callBack:
							callBack(firstByte + secondByte + remainingBytes)	
						else:
							print "No callBack defined for for modem command %s" % modemCommand					
						
					else:
						print "No responseSize defined for modem command %s" % modemCommand						
					
				else:
					print "Unknown first byte %s" % binascii.hexlify(firstByte[0])
			else:
				#print "Sleeping"
				time.sleep(0.1)

			
		self.__interfaceRunningEvent.clear()
								
	def __sendModemCommand(self, modemCommand, commandDataString = None, extraCommandDetails = None):		
		
		returnValue = False
		
		try:				
			bytesToSend = '\x02' + binascii.unhexlify(modemCommand)			
			if commandDataString != None:
				bytesToSend += commandDataString							
			commandHash = hashlib.sha224(bytesToSend).hexdigest()
						
			self.__commandLock.acquire()
			if self.__outboundCommandDetails.has_key(commandHash):
				#duplicate command.  Ignore
				pass
				
			else:				
				waitEvent = threading.Event()
				
				basicCommandDetails = { 'bytesToSend': bytesToSend, 'waitEvent': waitEvent, 'modemCommand': modemCommand }																														
				
				if extraCommandDetails != None:
					basicCommandDetails = dict(basicCommandDetails.items() + extraCommandDetails.items())						
				
				self.__outboundCommandDetails[commandHash] = basicCommandDetails
				
				self.__outboundQueue.append(commandHash)
				
				returnValue = {'commandHash': commandHash, 'waitEvent': waitEvent}
				
			self.__commandLock.release()						
					
		except Exception, ex:
			print traceback.format_exc()
			
		finally:
			
			#ensure that we unlock the thread lock
			#the code below will ensure that we have a valid lock before we call release
			self.__commandLock.acquire(False)
			self.__commandLock.release()
					
		return returnValue	
		
		
		
	def __sendStandardInsteonCommand(self, destinationDevice, commandId1, commandId2):				
		return self.__sendModemCommand('62', _stringIdToByteIds(destinationDevice) + _buildFlags() + binascii.unhexlify(commandId1) + binascii.unhexlify(commandId2), extraCommandDetails = { 'destinationDevice': destinationDevice, 'commandId1': commandId1, 'commandId2': commandId2})

			
	def __waitForCommandToFinish(self, commandExecutionDetails, timeout = None):
				
		if type(commandExecutionDetails) != type(dict()):
			print "Unable to wait without a valid commandExecutionDetails parameter"
			return False
			
		waitEvent = commandExecutionDetails['waitEvent']
		commandHash = commandExecutionDetails['commandHash']
		
		realTimeout = 4 #default timeout of 4 seconds
		if timeout:
			realTimeout = timeout
					
		if waitEvent.wait(realTimeout):	
			if self.__commandReturnData.has_key(commandHash):
				return self.__commandReturnData[commandHash]
			else:
				return True
		else:
			print "Timed out for %s" % commandHash
			return False
					
	def __process_PLMInfo(self, responseBytes):				
		(modemCommand, idHigh, idMid, idLow, deviceCat, deviceSubCat, firmwareVer, acknak) = struct.unpack('xBBBBBBBB', responseBytes)		
		
		foundCommandHash = None		
		#find our pending command in the list so we can say that we're done (if we are running in syncronous mode - if not well then the caller didn't care)
		for (commandHash, commandDetails) in self.__pendingCommandDetails.items():						
			if binascii.unhexlify(commandDetails['modemCommand']) == chr(modemCommand):
				#Looks like this is our command.  Lets deal with it.				
				self.__commandReturnData[commandHash] = { 'id': _byteIdToStringId(idHigh,idMid,idLow), 'deviceCategory': '%02X' % deviceCat, 'deviceSubCategory': '%02X' % deviceSubCat, 'firmwareVersion': '%02X' % firmwareVer }	
				
				waitEvent = commandDetails['waitEvent']
				waitEvent.set()
				
				foundCommandHash = commandHash
				break
				
		if foundCommandHash:
			del self.__pendingCommandDetails[foundCommandHash]
		else:
			print "Unable to find pending command details for the following packet:"
			print utilities.hex_dump(responseBytes, len(responseBytes))
			
	def __process_StandardInsteonMessagePLMEcho(self, responseBytes):				
		#print utilities.hex_dump(responseBytes, len(responseBytes))
		#we don't do anything here.  Just eat the echoed bytes
		pass
			
	def __process_InboundStandardInsteonMessage(self, responseBytes):
		(insteonCommand, fromIdHigh, fromIdMid, fromIdLow, toIdHigh, toIdMid, toIdLow, messageFlags, command1, command2) = struct.unpack('xBBBBBBBBBB', responseBytes)		
		
		foundCommandHash = None			
		waitEvent = None
		
		#find our pending command in the list so we can say that we're done (if we are running in syncronous mode - if not well then the caller didn't care)
		for (commandHash, commandDetails) in self.__pendingCommandDetails.items():
			#since this was a standard insteon message the modem command used to send it was a 0x62 so we check for that
			if binascii.unhexlify(commandDetails['modemCommand']) == '\x62':								
				#since there could be multiple insteon messages flying out over the wire, check to see if this one is from the device we send this command to
				destDeviceId = None
				if commandDetails.has_key('destinationDevice'):
					destDeviceId = commandDetails['destinationDevice']					
					
				if destDeviceId:
					if destDeviceId == _byteIdToStringId(fromIdHigh, fromIdMid, fromIdLow):
																		
						#check to see what kind of message this was (based on message flags)
						isBroadcast = messageFlags & (1 << 7) == (1 << 7)
						isDirect = not isBroadcast
						isAck = messageFlags & (1 << 5) == (1 << 5)
						isNak = isAck and isBroadcast
						
						returnData = {} #{'isBroadcast': isBroadcast, 'isDirect': isDirect, 'isAck': isAck}
						
						#try and look up a specific handler for this insteon command
						insteonCommandCode = "%02X" % command1
						if isBroadcast:
							#standard broadcast
							insteonCommandCode = 'SB' + insteonCommandCode
						else:
							#standard direct
							insteonCommandCode = 'SD' + insteonCommandCode
						
						#print insteonCommandCode					
							
						if self.__insteonCommands.has_key(insteonCommandCode):
							if self.__insteonCommands[insteonCommandCode].has_key('callBack'):
								(requestCycleDone, extraReturnData) = self.__insteonCommands[insteonCommandCode]['callBack'](responseBytes)
														
								if extraReturnData:
									returnData = dict(returnData.items() + extraReturnData.items())
								
								if requestCycleDone:									
									waitEvent = commandDetails['waitEvent']									
							else:
								print "No callBack for insteon command code %s" % insteonCommandCode	
						else:
							print "No insteonCommand lookup defined for insteon command code %s" % insteonCommandCode	
								
						if len(returnData):
							self.__commandReturnData[commandHash] = returnData
																												
						foundCommandHash = commandHash
						break
						
		if waitEvent:
			waitEvent.set()
			if foundCommandHash:
				del self.__pendingCommandDetails[foundCommandHash]
	
				
	#insteon message handlers
	def __handle_StandardDirect_IgnoreAck(self, messageBytes):
		#just ignore the ack for what ever command triggered us
		#there is most likley more data coming for what ever command we are handling
		return (False, None)
		
	def __handle_StandardDirect_AckCompletesCommand(self, messageBytes):
		#the ack for our command completes things.  So let the system know so
		return (True, None)							
					
	def __handle_StandardDirect_PingResponse(self, messageBytes):
		#ping juse returns an ack.  Nothing more.
		return (True, None)										
				
	def __handle_StandardDirect_IDRequest(self, messageBytes):
		#the request cycle isn't done yet.  We just eat this message (its just an ack, really we want the "set button pushed message")
		return (False, None)	
					
	def __handle_StandardBroadcast_SetButtonPressed(self, messageBytes):		
		#02 50 17 C4 4A 01 19 38 8B 01 00
		(idHigh, idMid, idLow, deviceCat, deviceSubCat, deviceRevision) = struct.unpack('xxBBBBBBxxx', messageBytes)
		return (True, {'deviceType': '%02X%02X' % (deviceCat, deviceSubCat), 'deviceRevision':'%02X' % deviceRevision})
			
	def __handle_StandardDirect_EngineResponse(self, messageBytes):		
		#02 50 17 C4 4A 18 BA 62 2B 0D 01		
		engineVersionIdentifier = messageBytes[10]			
		return (True, {'engineVersion': engineVersionIdentifier == '\x01' and 'i2' or 'i1'})
			
		
		
		
		
		
	#public methods		
	def getPLMInfo(self, timeout = None):		
		commandExecutionDetails = self.__sendModemCommand('60')
			
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)							
			
	def pingDevice(self, deviceId, timeout = None):		
		startTime = time.time()
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '0F', '00')				

		#Wait for ping result
		commandReturnCode = self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
		endTime = time.time()
		
		if commandReturnCode:
			return endTime - startTime
		else:
			return False
			
	def idRequest(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '10', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
		
	def getInsteonEngineVersion(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '0D', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
	
	def getProductData(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '03', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
			
	def lightStatusRequest(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '19', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)		
			
	def turnOn(self, deviceId, timeout = None):		
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '11', 'ff')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)			

	def turnOff(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '13', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)
	
	def turnOnFast(self, deviceId, timeout = None):		
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '12', 'ff')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)			

	def turnOffFast(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardInsteonCommand(deviceId, '14', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
			
			
			
			
			
			
			
		
#print _byteIdToStringId(24,186,97)
#print utilities.hex_dump(_stringIdToByteIds('18.ba.62'), len(_stringIdToByteIds('18.ba.62')));
	

pyI = CWInsteon('A6008a4L')

try:
	pyI.start()
	
	#tested
	#print pyI.getPLMInfo()	
	
	#untested
	#print pyI.getPLMConfig()
	#print pyI.setPLMConfig(enableMonitorMode = True)		
	#pyI.clearAllLinkDatabase()
	#pyI.addAllLinkRecord('17.C4.4A', 1, False, 0, 0, 0)
	#pyI.addAllLinkRecord('18.4f.16', 1, True, 0, 0, 0)
	#print pyI.getAllLinkDatabase()
	


	#tested	
	#print pyI.pingDevice('17.C4.4A')
	
	#tested	
	#print pyI.idRequest('17.C4.4A')
	
	#tested
	#print pyI.getInsteonEngineVersion('17.C4.4A')
	
	#tested
	#pyI.turnOn('17.C4.4A')
	#pyI.turnOff('17.C4.4A')	
	
	#untested
	#print pyI.getProductData('17.C4.4A')
	
	#still not working yet
	#print pyI.lightStatusRequest('17.C4.4A')	
	
	
	
	
	
		
	select.select([],[],[])
except Exception, ex: 
	print traceback.format_exc()
except KeyboardInterrupt:
	pass

pyI.shutdown()

