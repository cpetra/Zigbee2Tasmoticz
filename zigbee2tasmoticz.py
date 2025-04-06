try:
    import collections.abc as collections
except ImportError:  # Python <= 3.2 including Python 2
    import collections

errmsg = ""
try:
    import Domoticz
except Exception as e:
    errmsg += "Domoticz core start error: "+str(e)
#try:
#    import json
#except Exception as e:
#    errmsg += " Json import error: "+str(e)
#try:
#    import binascii
#except Exception as e:
#    errmsg += " binascii import error: "+str(e)


tasmotaDebug = True
DEVICE_TEMPERATURE = 80
DEVICE_HUMIDITY = 81
DEVICE_TEMP_HUM = 82
DEVICE_SWITCH = 244
DEVICE_TYPE_DIMMER = 7

# Decide if tasmota.py debug messages should be displayed if domoticz debug is enabled for this plugin
def setTasmotaDebug(flag):
    global tasmotaDebug
    tasmotaDebug = flag


# Replaces Domoticz.Debug() so tasmota related messages can be turned off from plugin.py
def Debug(msg):
    if tasmotaDebug:
        Domoticz.Debug(msg)


# Handles incoming Tasmota messages from MQTT or Domoticz commands for Tasmota devices
class Handler:
    def __init__(self, prefix1, prefix2, mqttClient, devices):
        Debug("Handler::__init__(cmnd: {}, tele: {})".format(
            prefix1, prefix2))

        if errmsg != "":
            Domoticz.Error(
                "Handler::__init__: Domoticz Python env error {}".format(errmsg))

        # So far only STATUS, STATE, SENSOR and RESULT are used. Others just for research...
#        self.topics = ['INFO1', 'STATE', 'SENSOR', 'RESULT', 'STATUS',
#                       'STATUS5', 'STATUS8', 'STATUS11', 'ENERGY']

        self.prefix = [None, prefix1, prefix2]
#        self.subscriptions = subscriptions
        self.mqttClient = mqttClient

        # I don't understand variable (in)visibility
        global Devices
        Devices = devices

    def debug(self, flag):
        global tasmotaDebug
        tasmotaDebug = flag

    # Translate domoticz command to tasmota mqtt command(s?)
    def onDomoticzCommand(self, Unit, Command, Level, Color):
        Debug("Handler::onDomoticzCommand: Unit: {}, Command: {}, Level: {}, Color: {}".format(
            Unit, Command, Level, Color))
        if Devices[Unit].Type == DEVICE_SWITCH:
            Debug("Switchtype {}".format(Devices[Unit].SwitchType))
            if Command == "On" or Command == "Off": #Devices[Unit].SwitchType == 0:
#                cmdnum= "1" if Command == "On" else "0"
                endpoint = None
                if 'Endpoint' in Devices[Unit].Options:
                    endpoint = Devices[Unit].Options['Endpoint']
                    payload="{ \"Device\":"+Devices[Unit].DeviceID+", \"Endpoint\":" + endpoint + ", \"Send\":{\"Power\":\""+Command+"\"} }"
                else:
                    payload="{ \"Device\":"+Devices[Unit].DeviceID+", \"Send\":{\"Power\":\""+Command+"\"} }"
                topic = self.prefix[1]+"/ZbSend"
                Domoticz.Log("Send Command {} to {}".format(Command,Devices[Unit].Name))
                Debug("Publish topic {} payload {}".format(topic,payload))
                self.mqttClient.publish(topic, payload)
            elif Command == "Set Level":
                payload="{ \"Device\":"+Devices[Unit].DeviceID+", \"Send\":{\"Dimmer\":"+str(int(Level*2.55))+"} }"
                topic = self.prefix[1]+"/ZbSend"
                Domoticz.Log("Send Command {} {} to {}".format(Command, str(int(Level*2.55)),Devices[Unit].Name))
                Debug("Publish topic {} payload {}".format(topic,payload))
                self.mqttClient.publish(topic, payload)
                if Level > 0 and Devices[Unit].nValue == 0: #we need to switch it on if it was off
                    payload="{ \"device\":"+Devices[Unit].DeviceID+", \"send\":{\"Power\":1} }"
                    self.mqttClient.publish(topic, payload)
        return True

    # Subscribe to our topics
    def onMQTTConnected(self):
        subs = []
        subs.append(self.prefix[2])
        Debug('Handler::onMQTTConnected: Subscriptions: {}'.format(repr(subs)))
        self.mqttClient.subscribe(subs)

    # Process incoming MQTT messages from Tasmota devices
    def onMQTTPublish(self, topic, message):
        Debug("Handler::onMQTTPublish: topic: {}, message {}".format(topic,message))
        if 'ZbReceived' in message:
            keys=list(message['ZbReceived'].keys())
            for key in keys:
                device = message['ZbReceived'][key]['Device'] if 'Device' in message['ZbReceived'][key] else None
                if 'Temperature' in message['ZbReceived'][key]:
                    updateTemp(device,message['ZbReceived'][key]['Temperature'], message['ZbReceived'][key]['Name'])
                if 'Humidity' in message['ZbReceived'][key]:
                    updateHumidity(device, message['ZbReceived'][key]['Humidity'], message['ZbReceived'][key]['Name'])
                if 'BatteryPercentage' in message['ZbReceived'][key]:
                    updateBatteryPercentage(device, message['ZbReceived'][key]['BatteryPercentage'])
                if 'BatteryVoltage' in message['ZbReceived'][key]:
                    updateBatteryVoltage(device, message['ZbReceived'][key]['BatteryVoltage'])
                if 'LinkQuality' in message['ZbReceived'][key]:
                    updateLinkQuality(device, message['ZbReceived'][key]['LinkQuality'])
                if 'Power' in message['ZbReceived'][key]:
                    if 'Endpoint' in message['ZbReceived'][key]:
                        updateSwitch(device, message['ZbReceived'][key]['Power'], message['ZbReceived'][key]['Name'], message['ZbReceived'][key]['Endpoint'])
                    else:
                        updateSwitch(device, message['ZbReceived'][key]['Power'], message['ZbReceived'][key]['Name'])
                if 'Dimmer' in message['ZbReceived'][key]:
                    updateDimmer(device, message['ZbReceived'][key]['Dimmer'], message['ZbReceived'][key]['Name'])

###########################
# Tasmota Utility functions


def updateTemp(shortaddr,temperature,friendlyname):
    create=True
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
           if Devices[idx].Type == DEVICE_TEMPERATURE: #Temperature
              Devices[idx].Update(nValue=0, sValue="{:.1f}".format(temperature))
              Domoticz.Log("Update Device {} Temperature {}".format(Devices[idx].Name,temperature))
           elif Devices[idx].Type == DEVICE_HUMIDITY: #Humidity
              Devices[idx].Update(TypeName="Temp+Hum",nValue=0, sValue="{:.1f};{};{}".format(temperature,Devices[idx].nValue,Devices[idx].sValue))
              Domoticz.Log("Update Device {} to Temp+Hum Temperature {}".format(Devices[idx].Name,temperature))
           elif Devices[idx].Type == DEVICE_TEMP_HUM: #Temp+Hum
              svalue=Devices[idx].sValue
              Debug("Temperature svalue: {}".format(svalue))
              parts=svalue.split(';')
              parts[0]="{:.1f}".format(temperature)
              svalue=";".join(parts)
              Devices[idx].Update(nValue=0, sValue=svalue)
              Domoticz.Log("Update Device {} Temperature {} {}".format(Devices[idx].Name,temperature, svalue))
           create=False
    if create:
        createDevice(deviceid=shortaddr,devicetype="Temperature",name=friendlyname,nvalue=0,svalue="{:.1f}".format(temperature))


def updateHumidity(shortaddr, humidity,friendlyname):
    create=True
    if humidity<40:
        humstat="2"
    elif humidity>60:
        humstat="3"
    else:
        humstat="1"
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
           if Devices[idx].Type == DEVICE_HUMIDITY: #Humidity
              Devices[idx].Update(nValue=int(round(humidity)), sValue=humstat)
              Domoticz.Log("Update Device {} Humidity {}".format(Devices[idx].Name,humidity))
           elif Devices[idx].Type == DEVICE_TEMPERATURE: #Temperature
              Devices[idx].Update(TypeName="Temp+Hum",nValue=0, sValue="{};{};{}".format(Devices[idx].sValue,int(round(humidity)),humstat))
              Domoticz.Log("Update Device {} to Temp+Hum Humidity {}".format(Devices[idx].Name,humidity))
           elif Devices[idx].Type == DEVICE_TEMP_HUM: #Temp+Hum
              svalue=Devices[idx].sValue
              Debug("Humidity svalue: {}".format(svalue))
              parts=svalue.split(';')
              parts[1]=str(round(humidity, 1))
              parts[2]=humstat
              svalue=";".join(parts)
              Devices[idx].Update(nValue=0, sValue=svalue)
              Domoticz.Log("Update Device {} Humidity {}, Svalue: {}".format(Devices[idx].Name,humidity,svalue))
           create=False
    if create:
        createDevice(deviceid=shortaddr,devicetype="Humidity",name=friendlyname,nvalue=int(round(humidity)),svalue=humstat)

def updateBatteryPercentage(shortaddr, battery_percentage):
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
           Devices[idx].Update(nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, BatteryLevel=int(battery_percentage))
           Debug("Update Device {} Battery Percentage: {}".format(Devices[idx].Name, battery_percentage))

def updateBatteryVoltage(shortaddr, battery_voltage): #do nothing
    Debug("Device: {}, Battery Voltage: {}".format(shortaddr, battery_voltage))

def updateLinkQuality(shortaddr, link_quality):
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
           Devices[idx].Update(nValue=Devices[idx].nValue, sValue=Devices[idx].sValue, SignalLevel=int(min(round(link_quality/254*12),12)))
           Debug("Device: {}, Link Quality: {}".format(Devices[idx].Name, link_quality))

def updateSwitch(shortaddr, power, friendlyname, endpoint=None):
    Debug("XDevice: {}, Power: {}, Endpoint: {}".format(shortaddr, power, endpoint))
    create=True
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
            Debug(f"Device data Options: {Devices[idx].Options}")
            if endpoint is not None:
                if 'Endpoint' in Devices[idx].Options:
                    if int(Devices[idx].Options['Endpoint']) != int(endpoint):
                        continue
            if Devices[idx].Type == DEVICE_SWITCH:
                if Devices[idx].SwitchType == DEVICE_TYPE_DIMMER:
                    Devices[idx].Update(nValue=power,sValue= Devices[idx].sValue)
                else:
                    if str(Devices[idx].nValue) != str(power): 
                        Devices[idx].Update(nValue=power,sValue="On" if power == 1 else "Off")
                        Domoticz.Log("Update switch {} nvalue {} svalue {} endpoint {}".format(friendlyname,power,"On" if power == 1 else "Off", endpoint))
            create=False
    if create:
        options = None
        if endpoint is not None:
            friendlyname = f"{friendlyname} {endpoint}"
            options = {"Endpoint": endpoint}
        createDevice(deviceid=shortaddr,devicetype="Switch",name=friendlyname,nvalue=power,svalue="",options=options)

def updateDimmer(shortaddr, dimmer, friendlyname): #dimmers are not created but only updated from existing switches
    Debug("Device: {}, Dimmer: {}".format(shortaddr, dimmer))
    for idx in Devices:
        if Devices[idx].DeviceID == shortaddr:
#           Debug("SwitchType {}".format(Devices[idx].SwitchType))
           if Devices[idx].Type == DEVICE_SWITCH:
               if Devices[idx].SwitchType !=7:
                   Devices[idx].Update(Subtype=73,Switchtype=7,sValue=str(int(round(dimmer/2.55))),nValue=Devices[idx].nValue)
               Devices[idx].Update(sValue=str(int(round(dimmer/2.55))),nValue=Devices[idx].nValue)
#               Devices[idx].Update(nValue=power,sValue="On" if power == 1 else "Off")
               Domoticz.Log("Update dimmer {}  {}".format(friendlyname,dimmer))


def createDevice(deviceid, devicetype, name, nvalue, svalue, options={}):
    Domoticz.Log("Create Device: {} {} options {}".format(name, devicetype, options))
    unit = findfreeUnit()
    Domoticz.Device(Name=name, Unit=unit, TypeName=devicetype, Used=1, DeviceID=deviceid, Options=options).Create()
    if unit in Devices:
        Domoticz.Log(f"Created device {name} type {devicetype}")
#        Devices[unit].Update(nValue=Devices[unit].nValue, sValue=Devices[unit].sValue, Name=name, SuppressTriggers=True)
        #Devices[unit].Update(nValue=nvalue, sValue=svalue)
#    for idx in Devices:
#        if Devices[idx].DeviceID == deviceid:
#           Devices[idx].Update(nValue=nvalue, sValue=svalue)

def findfreeUnit():
    for idx in range(1, 512):
        if idx not in Devices:
            break
    return idx
