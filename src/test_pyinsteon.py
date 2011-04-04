'''
Created on Mar 26, 2011

@author: jason@sharpee.com
'''
import select
from pyinsteon import PyInsteon, FTDI

pyI = PyInsteon(FTDI('A6008a4L'))

try:
	print pyI.getPLMInfo()
	print pyI.getPLMInfo()
	print pyI.getPLMInfo()
	
	select.select([],[],[])
except Exception, ex: 
	print ex
except KeyboardInterrupt:
	pass

pyI.shutdown()
