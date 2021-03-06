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
import sys
import string
import hashlib
from collections import deque

import utilities
import serial
#import pyftdi

def _byteIdToStringId(idHigh, idMid, idLow):
	return '%02X.%02X.%02X' % (idHigh, idMid, idLow)
	
def _cleanStringId(stringId):
	return stringId[0:2] + stringId[3:5] + stringId[6:8]

def _stringIdToByteIds(stringId):
	return binascii.unhexlify(_cleanStringId(stringId))
	
def _buildFlags():
	#todo: impliment this
	return '\x0f'
	
def hashPacket(packetData):
	return hashlib.md5(packetData).hexdigest()

def simpleMap(value, in_min, in_max, out_min, out_max):
	#stolen from the arduino implimentation.  I am sure there is a nice python way to do it, but I have yet to stublem across it				
	return (float(value) - float(in_min)) * (float(out_max) - float(out_min)) / (float(in_max) - float(in_min)) + float(out_min);

class CWInsteon(threading.Thread):
	
	def __init__(self, serialDevicePath):
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
								'51': {
									'responseSize':23,
									'callBack':self.__process_InboundExtendedInsteonMessage
								  },								
							}
		
		self.__insteonCommands = {
									#Direct Messages/Responses
									'SD03': {		#Product Data Request (generally an Ack)							
										'callBack' : self.__handle_StandardDirect_IgnoreAck
									},
									'SD0D': {		#Get Insteon Engine							
										'callBack' : self.__handle_StandardDirect_EngineResponse,
										'validResponseCommands' : ['SD0D']
									},
									'SD0F': {		#Ping Device						
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD0F']
									},
									'SD10': {		#ID Request	(generally an Ack)						
										'callBack' : self.__handle_StandardDirect_IgnoreAck,
										'validResponseCommands' : ['SD10', 'SB01']
									},	
									'SD11': {		#Devce On								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD11']
									},									
									'SD12': {		#Devce On Fast								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD12']
									},									
									'SD13': {		#Devce Off								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD13']
									},									
									'SD14': {		#Devce Off Fast								
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD14']									
									},
									'SD15': {		#Brighten one step
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD15']									
									},	
									'SD16': {		#Dim one step
										'callBack' : self.__handle_StandardDirect_AckCompletesCommand,
										'validResponseCommands' : ['SD16']									
									},								
									'SD19': {		#Light Status Response								
										'callBack' : self.__handle_StandardDirect_LightStatusResponse,
										'validResponseCommands' : ['SD19']
									},	
									
									#Broadcast Messages/Responses								
									'SB01': {	
													#Set button pushed								
										'callBack' : self.__handle_StandardBroadcast_SetButtonPressed
									},								   
								}
		
		
		self._allLinkDatabase = dict()
		
		self.__shutdownEvent = threading.Event()
		self.__interfaceRunningEvent = threading.Event()
		
		self.__commandLock = threading.Lock()
		self.__outboundQueue = deque()
		self.__outboundCommandDetails = dict()
		self.__retryCount = dict()		
		
		self.__pendingCommandDetails = dict()		
		
		self.__commandReturnData = dict()
		
		self.__intersend_delay = 0.15 #150 ms between network sends
		self.__lastSendTime = 0

		print "Using %s for PLM communication" % serialDevicePath
		self.__serialDevice = serial.Serial(serialDevicePath, 19200, timeout = 0.1)				
	
	def shutdown(self):
		if self.__interfaceRunningEvent.isSet():
			self.__shutdownEvent.set()

			#wait 2 seconds for the interface to shut down
			self.__interfaceRunningEvent.wait(2000)
			
	def run(self):
		self.__interfaceRunningEvent.set();
		
		#for checking for duplicate messages received in a row
		lastPacketHash = None
		
		while not self.__shutdownEvent.isSet():
			
			#check to see if there are any outbound messages to deal with
			self.__commandLock.acquire()
			if (len(self.__outboundQueue) > 0) and (time.time() - self.__lastSendTime > self.__intersend_delay):
				commandHash = self.__outboundQueue.popleft()
				
				commandExecutionDetails = self.__outboundCommandDetails[commandHash]
				
				bytesToSend = commandExecutionDetails['bytesToSend']
				print "> ", utilities.hex_dump(bytesToSend, len(bytesToSend)),

				self.__serialDevice.write(bytesToSend)					
				
				self.__pendingCommandDetails[commandHash] = commandExecutionDetails				
				del self.__outboundCommandDetails[commandHash]
				
				self.__lastSendTime = time.time()
								
			self.__commandLock.release()	
			
			#check to see if there is anyting we need to read			
			firstByte = self.__serialDevice.read(1)			
			if len(firstByte) == 1:
				#got at least one byte.  Check to see what kind of byte it is (helps us sort out how many bytes we need to read now)
									
				if firstByte[0] == '\x02':
					#modem command (could be an echo or a response)
					#read another byte to sort that out
					secondByte = self.__serialDevice.read(1)
										
					responseSize = -1
					callBack = None
					
					modemCommand = binascii.hexlify(secondByte).upper()
					if self.__modemCommands.has_key(modemCommand):
						if self.__modemCommands[modemCommand].has_key('responseSize'):																	
							responseSize = self.__modemCommands[modemCommand]['responseSize']							
						if self.__modemCommands[modemCommand].has_key('callBack'):																	
							callBack = self.__modemCommands[modemCommand]['callBack']							
							
					if responseSize != -1:						
						remainingBytes = self.__serialDevice.read(responseSize)
						
						print "< ",
						print utilities.hex_dump(firstByte + secondByte + remainingBytes, len(firstByte + secondByte + remainingBytes)),
						
						currentPacketHash = hashPacket(firstByte + secondByte + remainingBytes)
						if lastPacketHash and lastPacketHash == currentPacketHash:
							#duplicate packet.  Ignore
							pass
						else:						
							if callBack:
								callBack(firstByte + secondByte + remainingBytes)	
							else:
								print "No callBack defined for for modem command %s" % modemCommand		
						
						lastPacketHash = currentPacketHash			
						
					else:
						print "No responseSize defined for modem command %s" % modemCommand						
				elif firstByte[0] == '\x15':
					print "Received a Modem NAK!"
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
			commandHash = hashPacket(bytesToSend)
						
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
				self.__retryCount[commandHash] = 0
				
				print "Queued %s" % commandHash
				
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
		
		
		
	def __sendStandardP2PInsteonCommand(self, destinationDevice, commandId1, commandId2):				
		return self.__sendModemCommand('62', _stringIdToByteIds(destinationDevice) + _buildFlags() + binascii.unhexlify(commandId1) + binascii.unhexlify(commandId2), extraCommandDetails = { 'destinationDevice': destinationDevice, 'commandId1': 'SD' + commandId1, 'commandId2': commandId2})

			
	def __waitForCommandToFinish(self, commandExecutionDetails, timeout = None):
				
		if type(commandExecutionDetails) != type(dict()):
			print "Unable to wait without a valid commandExecutionDetails parameter"
			return False
			
		waitEvent = commandExecutionDetails['waitEvent']
		commandHash = commandExecutionDetails['commandHash']
		
		realTimeout = 2 #default timeout of 2 seconds
		if timeout:
			realTimeout = timeout
			
		timeoutOccured = False
		
		if sys.version_info[:2] > (2,6):
			#python 2.7 and above waits correctly on events
			timeoutOccured = not waitEvent.wait(realTimeout)
		else:
			#< then python 2.7 and we need to do the waiting manually
			while not waitEvent.isSet() and realTimeout > 0:
				time.sleep(0.1)
				realTimeout -= 0.1
				
			if realTimeout == 0:
				timeoutOccured = True
					
		if not timeoutOccured:	
			if self.__commandReturnData.has_key(commandHash):
				return self.__commandReturnData[commandHash]
			else:
				return True
		else:			
			#re-queue the command to try again
			self.__commandLock.acquire()
			
			if self.__retryCount[commandHash] >= 5:
				#too many retries.  Bail out
				self.__commandLock.release()
				return False
				
			print "Timed out for %s - Requeueing (already had %d retries)" % (commandHash, self.__retryCount[commandHash])
			
			requiresRetry = True
			if self.__pendingCommandDetails.has_key(commandHash):
				
				self.__outboundCommandDetails[commandHash] = self.__pendingCommandDetails[commandHash]
				del self.__pendingCommandDetails[commandHash]
			
				self.__outboundQueue.append(commandHash)
				self.__retryCount[commandHash] += 1
			else:
				print "Interesting.  timed out for %s, but there is no pending command details" % commandHash
				#to prevent a huge loop here we bail out
				requiresRetry = False
			
			self.__commandLock.release()
			
			if requiresRetry:
				return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)
			else:
				return False
		
			




	#low level processing methods
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
			
		
	def __validResponseMessagesForCommandId(self, commandId):
		if self.__insteonCommands.has_key(commandId):
			commandInfo = self.__insteonCommands[commandId]
			if commandInfo.has_key('validResponseCommands'):
				return commandInfo['validResponseCommands']
		
		return False
		
	def __process_InboundStandardInsteonMessage(self, responseBytes):
		(insteonCommand, fromIdHigh, fromIdMid, fromIdLow, toIdHigh, toIdMid, toIdLow, messageFlags, command1, command2) = struct.unpack('xBBBBBBBBBB', responseBytes)		
		
		foundCommandHash = None			
		waitEvent = None
		
		#check to see what kind of message this was (based on message flags)
		isBroadcast = messageFlags & (1 << 7) == (1 << 7)
		isDirect = not isBroadcast
		isAck = messageFlags & (1 << 5) == (1 << 5)
		isNak = isAck and isBroadcast
		
		insteonCommandCode = "%02X" % command1
		if isBroadcast:
			#standard broadcast
			insteonCommandCode = 'SB' + insteonCommandCode
		else:
			#standard direct
			insteonCommandCode = 'SD' + insteonCommandCode
			
		if insteonCommandCode == 'SD00':
			#this is a strange special case...
			#lightStatusRequest returns a standard message and overwrites the cmd1 and cmd2 bytes with "data"
			#cmd1 (that we use here to sort out what kind of incoming message we got) contains an 
			#"ALL-Link Database Delta number that increments every time there is a change in the addressee's ALL-Link Database"
			#which makes is super hard to deal with this response (cause cmd1 can likley change)
			#for now my testing has show that its 0 (at least with my dimmer switch - my guess is cause I haven't linked it with anything)
			#so we treat the SD00 message special and pretend its really a SD19 message (and that works fine for now cause we only really
			#care about cmd2 - as it has our light status in it)
			insteonCommandCode = 'SD19'
		
		#print insteonCommandCode					
		
		#find our pending command in the list so we can say that we're done (if we are running in syncronous mode - if not well then the caller didn't care)
		for (commandHash, commandDetails) in self.__pendingCommandDetails.items():
			
			#since this was a standard insteon message the modem command used to send it was a 0x62 so we check for that
			if binascii.unhexlify(commandDetails['modemCommand']) == '\x62':																		
				originatingCommandId1 = None
				if commandDetails.has_key('commandId1'):
					originatingCommandId1 = commandDetails['commandId1']	
					
				validResponseMessages = self.__validResponseMessagesForCommandId(originatingCommandId1)
				if validResponseMessages and len(validResponseMessages):
					#Check to see if this received command is one that this pending command is waiting for
					if validResponseMessages.count(insteonCommandCode) == 0:
						#this pending command isn't waiting for a response with this command code...  Move along
						continue
				else:
					print "Unable to find a list of valid response messages for command %s" % originatingCommandId1
					continue
						
					
				#since there could be multiple insteon messages flying out over the wire, check to see if this one is from the device we send this command to
				destDeviceId = None
				if commandDetails.has_key('destinationDevice'):
					destDeviceId = commandDetails['destinationDevice']
						
				if destDeviceId:
					if destDeviceId == _byteIdToStringId(fromIdHigh, fromIdMid, fromIdLow):
																		
						returnData = {} #{'isBroadcast': isBroadcast, 'isDirect': isDirect, 'isAck': isAck}
						
						#try and look up a handler for this command code
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
			
		if foundCommandHash == None:
			print "Unhandled packet (couldn't find any pending command to deal with it)"
			print "This could be an unsolocicited broadcast message"
						
		if waitEvent and foundCommandHash:
			waitEvent.set()			
			del self.__pendingCommandDetails[foundCommandHash]
			
			print "Command %s completed" % foundCommandHash
	
	def __process_InboundExtendedInsteonMessage(self, responseBytes):
		#51 
		#17 C4 4A 	from
		#18 BA 62 	to
		#50 		flags
		#FF 		cmd1
		#C0 		cmd2
		#02 90 00 00 00 00 00 00 00 00 00 00 00 00	data
		(insteonCommand, fromIdHigh, fromIdMid, fromIdLow, toIdHigh, toIdMid, toIdLow, messageFlags, command1, command2, data) = struct.unpack('xBBBBBBBBBB14s', responseBytes)		
		
		pass
		
				
		
		
		
				
	#insteon message handlers
	def __handle_StandardDirect_IgnoreAck(self, messageBytes):
		#just ignore the ack for what ever command triggered us
		#there is most likley more data coming for what ever command we are handling
		return (False, None)
		
	def __handle_StandardDirect_AckCompletesCommand(self, messageBytes):
		#the ack for our command completes things.  So let the system know so
		return (True, None)							
													
	def __handle_StandardBroadcast_SetButtonPressed(self, messageBytes):		
		#02 50 17 C4 4A 01 19 38 8B 01 00
		(idHigh, idMid, idLow, deviceCat, deviceSubCat, deviceRevision) = struct.unpack('xxBBBBBBxxx', messageBytes)
		return (True, {'deviceType': '%02X%02X' % (deviceCat, deviceSubCat), 'deviceRevision':'%02X' % deviceRevision})
			
	def __handle_StandardDirect_EngineResponse(self, messageBytes):		
		#02 50 17 C4 4A 18 BA 62 2B 0D 01		
		engineVersionIdentifier = messageBytes[10]			
		return (True, {'engineVersion': engineVersionIdentifier == '\x01' and 'i2' or 'i1'})
			
	def __handle_StandardDirect_LightStatusResponse(self, messageBytes):
		#02 50 17 C4 4A 18 BA 62 2B 00 00
		lightLevelRaw = messageBytes[10]	
		
		#map the lightLevelRaw value to a sane value between 0 and 1
		normalizedLightLevel = simpleMap(ord(lightLevelRaw), 0, 255, 0, 1)
					
		return (True, {'lightStatus': round(normalizedLightLevel, 2) })
		
		
		
		
		
	#public methods		
	def getPLMInfo(self, timeout = None):		
		commandExecutionDetails = self.__sendModemCommand('60')
			
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)							
			
	def pingDevice(self, deviceId, timeout = None):		
		startTime = time.time()
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '0F', '00')				

		#Wait for ping result
		commandReturnCode = self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
		endTime = time.time()
		
		if commandReturnCode:
			return endTime - startTime
		else:
			return False
			
	def idRequest(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '10', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
		
	def getInsteonEngineVersion(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '0D', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
	
	def getProductData(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '03', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
			
	def lightStatusRequest(self, deviceId, timeout = None):				
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '19', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)		
					
	def turnOn(self, deviceId, timeout = None):		
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '11', 'ff')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)			

	def turnOff(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '13', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)
	
	def turnOnFast(self, deviceId, timeout = None):		
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '12', 'ff')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)			

	def turnOffFast(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '14', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)	
			
	def dimTo(self, deviceId, level, timeout = None):
		
		#organize what dim level we are heading to (figgure out the byte we need to send)
		lightLevelByte = simpleMap(level, 0, 1, 0, 255)
		
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '11', '%02x' % lightLevelByte)						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)		
			
	def brightenOneStep(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '15', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)
	
	def dimOneStep(self, deviceId, timeout = None):
		commandExecutionDetails = self.__sendStandardP2PInsteonCommand(deviceId, '16', '00')						
		return self.__waitForCommandToFinish(commandExecutionDetails, timeout = timeout)			
			
			
			
		
print "Using Python: " + str(sys.version_info[0]) + '.' + str(sys.version_info[1]) + '.' + str(sys.version_info[2])	
pyI = CWInsteon('/dev/ttyUSB2')

#test device id
testDeviceId = '17.C4.4A'

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
	#print pyI.pingDevice('18.4f.16')
	
	#tested	
	#print pyI.idRequest('17.C4.4A')
	
	#tested
	#print pyI.getInsteonEngineVersion('17.C4.4A')
	
	#tested
	#pyI.turnOn('17.C4.4A')
	#pyI.turnOff('17.C4.4A')	
	
	#tested
	#pyI.dimTo('17.C4.4A', .5)
	
	#tested
	#pyI.brightenOneStep('17.C4.4A')
	#pyI.dimOneStep('17.C4.4A')
	
	#untested
	#print pyI.getProductData('17.C4.4A')
	
	#tested (but has an interesting workaround because of mangled command bytes in the response)
	#print pyI.lightStatusRequest('17.C4.4A')	
	
	keepRunning = True			
	while keepRunning:
		i,o,e = select.select([sys.stdin],[],[],0.0001)
		for s in i:
			if s == sys.stdin:				
				inputByte = sys.stdin.readline() 				
				
				if inputByte[0] == 'o':
					#turn light on
					pyI.turnOn(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'oo':
					#turn light on fast
					pyI.turnOnFast(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'f':
					#turn light off
					pyI.turnOff(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'ff':
					#turn light off fast
					pyI.turnOffFast(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'b':
					#brighten one step
					pyI.brightenOneStep(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'd':
					#dim one step
					pyI.dimOneStep(testDeviceId)
					print pyI.lightStatusRequest(testDeviceId)
				
				elif inputByte[0] == 'p':
					#ping device 
					print pyI.pingDevice(testDeviceId)
					
				elif inputByte[0] == 'i':
					#get device id 
					print pyI.idRequest(testDeviceId)
					
				elif inputByte[0] == 'w':
					#dim to 50%
					pyI.dimTo(testDeviceId, .5)
					print pyI.lightStatusRequest(testDeviceId)
					
				elif inputByte[0] == 'e':
					#get engine verison
					print pyI.getInsteonEngineVersion(testDeviceId)					
															
				elif inputByte[0] == 'q':
					#quit
					keepRunning = False						         				
	
except Exception, ex: 
	print traceback.format_exc()
except KeyboardInterrupt:
	pass


 
pyI.shutdown()

