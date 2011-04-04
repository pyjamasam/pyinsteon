'''
Created on Mar 26, 2011

@author: jason@sharpee.com
'''
import select
import traceback
from pyinsteon import PyInsteon, FTDI

def insteon_received(*params):
	print 'Insteon Received:', params


pyI = PyInsteon(FTDI('A6008a4L'))
pyI.onReceivedInsteon(insteon_received)

try:
	print pyI.getPLMInfo()
	#print pyI.sendInsteon("18.4F.14", False, None, None, 5, 5,  '0D', '00')
	print pyI.sendInsteon("17.C4.4A", False, None, None, 5, 5,  '0D', '00')
	
	
	#print pyI.getPLMInfo()
	#print pyI.getPLMInfo()
	
	select.select([],[],[])
except Exception, ex: 
	print traceback.format_exc()
except KeyboardInterrupt:
	pass

pyI.shutdown()
