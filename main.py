import httplib, urllib
import time, datetime, sys
import serial
from xbee import xbee
import sensorhistory
import optparse
from datetime import datetime
from time import sleep, localtime, strftime

API_KEY = "SBK6PW8UFZQ81MZR" #API Key for ThingSpeak
API_URL = "api.thingspeak.com:80" #API URL

ENERGY_PRICE = 0.30 #needs to be set by user at later date (cost per kWh)

LOG_FILE = "log_power.csv" # store data in logfile

SERIALPORT = "/dev/cu.usbserial-FTXKEMPL" #USB Serial port -> XBEE
BAUDRATE = 9600
CURRENTSENSE = 4
VOLTSENSE = 0
MAINSVPP = 325 * 2 #sqrt(2)*230 (RMS->VPP)
vrefcalibration = [494,  #Voltage
                   480,  #Current
                   489,  #2
                   492,  #3
                   501,  #4
                   493]  #etc
CURRENTNORM = 15.5  # Amperes <- ADC


# open up the FTDI serial port to get data transmitted to xbee
ser = serial.Serial(SERIALPORT, BAUDRATE)
ser.open()

# open our datalogging file
logfile = None
try:
    logfile = open(LOG_FILE, 'r+')
except IOError:
    # didn't exist yet
    logfile = open(LOG_FILE, 'w+')
    logfile.write("#Date, time, sensornum, avgWatts\n");
    logfile.flush()

sensorhistories = sensorhistory.SensorHistories(logfile)
print sensorhistories

def update_graph(idleevent):
    global avgwattdataidx, sensorhistories

#get one packet from the xbee or timeout
    packet = xbee.find_packet(ser)
    if not packet:
        return #timeout

    xb = xbee(packet) #parse
    #print xb.address_16

#n-1 samples as first one is not correct
    voltagedata = [-1] * (len(xb.analog_samples) - 1)
    ampdata = [-1] * (len(xb.analog_samples ) -1)

#store in arrays
    for i in range(len(voltagedata)):
        voltagedata[i] = xb.analog_samples[i+1][VOLTSENSE]
        ampdata[i] = xb.analog_samples[i+1][CURRENTSENSE]

    min_v = 1024
    max_v = 0

#normalising data
    for i in range(len(voltagedata)):
        if (min_v > voltagedata[i]):
            min_v = voltagedata[i]
        if (max_v < voltagedata[i]):
            max_v = voltagedata[i]

#average of min & max voltage

    avgv = (max_v + min_v) / 2
    vpp =  max_v-min_v

    for i in range(len(voltagedata)):

        voltagedata[i] -= avgv #remove DC Bias
        voltagedata[i] = (voltagedata[i] * MAINSVPP) / vpp

#normailse current

    for i in range(len(ampdata)):
        if vrefcalibration[xb.address_16]:
            ampdata[i] -= vrefcalibration[xb.address_16]
        else:
            ampdata[i] -= vrefcalibration[0]

        ampdata[i] /= CURRENTNORM

    #print "Voltage: ", voltagedata
    #print "Current: ", ampdata

#calculate power

    wattdata = [0] * len(voltagedata)
    for i in range(len(wattdata)):
        wattdata[i] = voltagedata[i] * ampdata[i]

#sum current over 1/50Hz
    avgamp = 0
#17 cycles per seccond

    for i in range(17):
        avgamp += abs(ampdata[i])
    avgamp /= 17.0

#sum power over 1/50Hz
    avgwatt = 0

#17 cycles per seccond

    for i in range(17):
        avgwatt += abs(wattdata[i])
    avgwatt /= 17.0

    print str(xb.address_16)+"\tCurrent draw, in amperes: "+str(avgamp)
    print "\tWatt draw, in VA: "+str(avgwatt)
    
    if (avgamp > 13):
        return

    sensorhistory = sensorhistories.find(xb.address_16)
    #print sensorhistory

    elapsedseconds = time.time() - sensorhistory.lasttime
    dwatthr = (avgwatt * elapsedseconds) / (60.0 * 60.0)  # 60 seconds in 60 minutes = 1 hr
    sensorhistory.lasttime = time.time()
    print "\t\tWh used in last ",elapsedseconds," seconds: ",dwatthr
    sensorhistory.addwatthr(dwatthr)

# Determine the minute of the hour (ie 6:42 -> '42')
    currminute = (int(time.time())/60) % 10
    currentSecond= datetime.now().second

    print currentSecond

    if (currentSecond == 30) or (currentSecond == 29) or (currentSecond == 0) or (currentSecond == 1):
        wattsused = 0
        whused = 0
        for history in sensorhistories.sensorhistories:
                wattsused += history.avgwattover5min()
                whused += history.dayswatthr
        
        kwhused = whused/1000
        avgwatt = (sensorhistory.avgwattover5min()-3)
        cost = kwhused * ENERGY_PRICE
        cost = "%.2f" % cost

        params = urllib.urlencode({'field1': kwhused, 'field2': cost, 'field3':avgwatt, 'key': API_KEY})
        headers = {"content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}
        conn = httplib.HTTPConnection(API_URL)

        try:
            conn.request("POST", "/update", params, headers)
            response = conn.getresponse()
            print response.status, response.reason
            data = response.read()
            conn.close()
        except:
            print "connection failed"



# Print out debug data, Wh used in last 5 minutes
        avgwattsused = sensorhistory.avgwattover5min()
        print time.strftime("%Y %m %d, %H:%M")+", "+str(sensorhistory.sensornum)+", "+str(sensorhistory.avgwattover5min())+"\n"
        
# Lets log it! Seek to the end of our log file
        if logfile:
            logfile.seek(0, 2) # 2 == SEEK_END. ie, go to the end of the file
            logfile.write(time.strftime("%Y %m %d, %H:%M")+", "+
                        str(sensorhistory.sensornum)+", "+
                        str(sensorhistory.avgwattover5min())+"\n")
            logfile.flush()

        sensorhistory.reset5mintimer()

if __name__ == "__main__":
     while True:
             update_graph(None)
	                  
