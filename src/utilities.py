
import time
import re

## {{{ http://code.activestate.com/recipes/142812/ (r1)
FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def hex_dump(src, length=8):
    N=0; result=''
    while src:
       s,src = src[:length],src[length:]
       hexa = ' '.join(["%02X"%ord(x) for x in s])
       s = s.translate(FILTER)
       result += "%04X   %-*s   %s\n" % (N, length*3, hexa, s)
       N+=length
    return result

## end of http://code.activestate.com/recipes/142812/ }}}

def interruptibleSleep(sleepTime, interuptEvent):
	sleepInterval = 0.05
	
	#adjust for the time it takes to do our instructions and such
	totalSleepTime = sleepTime - 0.04
	
	while interuptEvent.isSet() == False and totalSleepTime > 0:
		time.sleep(sleepInterval)
		totalSleepTime = totalSleepTime - sleepInterval
		
		
def sort_nicely( l ): 
	""" Sort the given list in the way that humans expect. 
	""" 
	convert = lambda text: int(text) if text.isdigit() else text 
	alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ] 
	l.sort( key=alphanum_key )

	return l
	
def convertStringFrequencyToSeconds(textFrequency):
	frequencyNumberPart = int(textFrequency[:-1])
	frequencyStringPart = textFrequency[-1:].lower()
	
	if (frequencyStringPart == "w"):
		frequencyNumberPart *= 604800
	elif (frequencyStringPart == "d"):
		frequencyNumberPart *= 86400
	elif (frequencyStringPart == "h"):
		frequencyNumberPart *= 3600						
	elif (frequencyStringPart == "m"):
		frequencyNumberPart *= 60
		
	return frequencyNumberPart
