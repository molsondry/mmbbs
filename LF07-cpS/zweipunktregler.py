import RPi.GPIO as GPIO
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe

class Zpr():
    def __init__(self, setpoint, hysteresis):
        self.splow=float(setpoint) # untere Grenze
        self.hyst=float(hysteresis) #Hysterese speichern
        self.sphigh=float(setpoint)+float(hysteresis) # obere Grenze
        self.state=False  # Reglerausgang per default ausschalten

    def kuehlen(self, temperature):
        # wird True zurückgeben, wenn gekühlt werden muss
        if temperature <= self.splow:
            self.state=False # Kühlung ausschalten, wenn es kalt ist
        elif temperature > self.sphigh:
            self.state=True # Kühlung einschalten, wenn es zu warm wird
        return self.state # Wenn der Regler im Bereich der Hysterese liegt, nichts am Zustand ändern

    def set_splow (self,setpoint):
        self.splow=float(setpoint)
    def set_hyst (self, hysteresis):
        self.hyst=float(hysteresis)
    def set_sphigh (self):
        self.sphigh=self.splow+self.hyst
# ********************* Ende class Zpr

class Fan():
    def __init__(self, gpio):
        self.state = False # Lüfter per default ausschalten
        self.gpio = gpio # GPIO Nr. des Lüfters
        GPIO.setmode(GPIO.BCM) # mit GPIO Bezeichnungen arbeiten
        GPIO.setup(self.gpio, GPIO.OUT) # Fan GPIO als Ausgang schalten
        self.off(self)
 
    def set_gpioState(self):        
        if (self.state==True):
            GPIO.output(self.gpio, 1) # GPIO.HIGH
        else:
            GPIO.output(self.gpio, 0) # GPIO.LOW

    def on(self):
        self.state = True # Lüfter an
        self.set_gpioState() # hier nun die GPIO-Ansteuerung rein

    def off(self):
        self.state = False # Lüfter aus
        self.set_gpioState() # hier nun die GPIO-Ansteuerung rein

    def get_state(self):
        return self.state    
# ********************* Ende class Fan

class Ds18b20():
    def __init__(self, w1_address):
        self.w1_address=w1_address
        self.w1_dir = '/sys/bus/w1/devices/' + self.w1_address + '/w1_slave'
        self.tempCelsius = 255.0

    def get_celsius(self) : 
        # cat self.w1_dir würde vom DS18B20 liefern:
        # 75 01 4b 46 7f ff 0b 10 78 : crc=78 YES
        # 75 01 4b 46 7f ff 0b 10 78 t=23312
        # Die Zahl hinter t= entspricht der Temperatur in tausendstel °C
        f = open(self.w1_dir, 'r') # "Datei" öffnen
        lines = f.readlines()
        # Warten bis in der ersten Zeile ein YES erscheint. Dann sind die Daten gültig
        while lines[0].strip()[-3:] != 'YES': 
            time.sleep(0.2)
            lines = f.readlines()

        tempStr = lines[1].find('t=')
        if tempStr != -1:
            # einen richtigen Wert gefunden
            self.tempCelsius = float(lines[1][tempStr+2:]) / 1000.0
        else:
            self.tempCelsius = 255.0

        return self.tempCelsius
# ********************* Ende class Ds18b20

class Cloud():
    # in dieser Klasse realisiert mit einem MQTT Broker
    def __init__(self, hostname, basetopic):
        self.roomTemp=255.0
        self.setpointTemp=255.0
        self.hyst=255.0
        self.gpioFan=0
        self.hostname=hostname
        basetopic = basetopic + "/"
        self.topicRoomTemp = basetopic + "roomtemp"
        self.topicSetpointTemp = basetopic + "setpointtemp"
        self.topicHyst = basetopic + "hyst"
        self.topicGpioFan = basetopic + "gpiofan"

    def get_roomTemp(self): # Serverraumtemperatur aus der Cloud lesen
        self.roomTemp = float((subscribe.simple(self.topicRoomTemp, hostname=self.hostname, retained=True)).payload)
        return self.roomTemp
    def set_roomTemp(self, temp): # Serverraumtemperatur in Cloud schreiben (macht eigentlich nur Sinn, wenn auf diesem Raspi die Temperaturmessung stattfindet)
        publish.single(self.topicRoomTemp, temp, hostname=self.hostname, retain=True)
        return

    def get_setpointTemp(self): # Solltemperatur aus der Cloud lesen
        self.setpointTemp = float((subscribe.simple(self.topicSetpointTemp, hostname=self.hostname, retained=True)).payload)
        return self.setpointTemp
    def set_setpointTemp(self, setpointTemp): # Solltemperatur in die Cloud schreiben
        publish.single(self.topicSetpointTemp, setpointTemp, hostname=self.hostname, retain=True)
        return
        
    def get_hyst(self): # Hysterese aus der Cloud lesen
        self.hyst = float((subscribe.simple(self.topicHyst, hostname=self.hostname, retained=True)).payload)
        return self.hyst
    def set_hyst(self, hyst): # Hysterese in die Cloud schreiben
        publish.single(self.topicHyst, hyst, hostname=self.hostname, retain=True)
        return

    def get_gpioFan(self):
        self.gpioFan = int((subscribe.simple(self.topicGpioFan, hostname=self.hostname, retained=True)).payload)
        return self.gpioFan
    def set_gpioFan(self, gpioFan): # GPIO Kanal für Ventilator in die Cloud schreiben
        publish.single(self.topicGpioFan, gpioFan, hostname=self.hostname, retain=True)
        return

# ********************* Ende class Cloud
def main():
    mycloud=Cloud("localhost", "serverraum/1")
    mycloud.set_setpointTemp(20)
    mycloud.set_hyst(3)
    mycloud.set_gpioFan(18) # das ist auch der Pin für PWM

    zpr=Zpr(mycloud.get_setpointTemp(),mycloud.get_hyst()) # Sollwert und Hysterese
    fan=Fan(mycloud.get_gpioFan())
    tempsen1=Ds18b20("28-000006dccb21")

    while True:
        mycloud.set_roomTemp(tempsen1.get_celsius()) # aktuelle Temperatur in die Cloud schreiben

        temp=float(mycloud.get_roomTemp())
        if (zpr.kuehlen(temp)==True):
            fan.on()
            print ("Fan ist an")
        else:
            fan.off()   
            print ("Fan ist aus")
        print ("Temp.: ", mycloud.get_roomTemp())

# ********************* Ende Funktion main()

#  ********************* Hauptprogramm
if __name__ == '__main__':
    main()
    