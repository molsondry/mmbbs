import RPi.GPIO as GPIO
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe
import time

class Zpr():
    def __init__(self, setpoint, hysteresis):
        self.__splow=float(setpoint) # untere Grenze
        self.__hyst=float(hysteresis) #Hysterese speichern
        self.set_sphigh() # obere Grenze
        self.__state=False  # Reglerausgang per default ausschalten

    def kuehlen(self, temperature):
        # wird True zurückgeben, wenn gekühlt werden muss
        if temperature <= self.__splow:
            self.state=False # Kühlung ausschalten, wenn es kalt ist
        elif temperature > self.__sphigh:
            self.__state=True # Kühlung einschalten, wenn es zu warm wird
        return self.__state # Wenn der Regler im Bereich der Hysterese liegt, nichts am Zustand ändern

    def set_splow (self,setpoint):
        self.__splow=float(setpoint)
    def set_hyst (self, hysteresis):
        self.__hyst=float(hysteresis)
    def set_sphigh (self):
        self.__sphigh=self.__splow+self.__hyst
# ********************* Ende class Zpr

class Fan():
    def __init__(self, gpio):
        self.__state = False # Lüfter per default ausschalten
        self.__gpio = gpio # GPIO Nr. des Lüfters
        GPIO.setmode(GPIO.BCM) # mit GPIO Bezeichnungen arbeiten
        GPIO.setup(self.__gpio, GPIO.OUT) # Fan GPIO als Ausgang schalten
        self.off()
 
    def __set_gpioState(self):        
        if (self.__state==True):
            GPIO.output(self.__gpio, 1) # GPIO.HIGH
        else:
            GPIO.output(self.__gpio, 0) # GPIO.LOW

    def on(self):
        self.__state = True # Lüfter an
        self.__set_gpioState() # hier nun die GPIO-Ansteuerung rein

    def off(self):
        self.__state = False # Lüfter aus
        self.__set_gpioState() # hier nun die GPIO-Ansteuerung rein

    def get_state(self):
        return self.__state    
# ********************* Ende class Fan

class Ds18b20():
    def __init__(self, w1_address):
        self.__w1_address=w1_address
        self.__w1_dir = '/sys/bus/w1/devices/' + self.__w1_address + '/w1_slave'
        self.__tempCelsius = 255.0

    def get_celsius(self) : 
        # cat self.w1_dir würde vom DS18B20 liefern:
        # 75 01 4b 46 7f ff 0b 10 78 : crc=78 YES
        # 75 01 4b 46 7f ff 0b 10 78 t=23312
        # Die Zahl hinter t= entspricht der Temperatur in tausendstel °C
        f = open(self.__w1_dir, 'r') # "Datei" öffnen
        lines = f.readlines()
        # Warten bis in der ersten Zeile ein YES erscheint. Dann sind die Daten gültig
        while lines[0].strip()[-3:] != 'YES': 
            time.sleep(0.2)
            lines = f.readlines()

        tempStr = lines[1].find('t=')
        if tempStr != -1:
            # einen richtigen Wert gefunden
            self.__tempCelsius = float(lines[1][tempStr+2:]) / 1000.0
        else:
            self.__tempCelsius = 255.0

        return self.__tempCelsius
# ********************* Ende class Ds18b20

class Cloud():
    # in dieser Klasse realisiert mit einem MQTT Broker
    def __init__(self, hostname, basetopic):
        self.__roomTemp=255.0 # Isttemperatur
        self.__setpointTemp=255.0 # Solltemperatur
        self.__hyst=255.0 #Hysterese
        self.__gpioFan=0 # GPIO BCM-Nr zur Lüfteransteuerung
        self.__hostname=hostname # Name/ IP des MQTT Brokers
        basetopic = basetopic + "/" # Basistopic für das Abspeichern der Werte
        self.__topicRoomTemp = basetopic + "roomtemp" # Topic für die Raumtemperatur
        self.__topicSetpointTemp = basetopic + "setpointtemp" # Topic für die Solltemperatur
        self.__topicHyst = basetopic + "hyst" # Topic für die Hysterese
        self.__topicGpioFan = basetopic + "gpiofan" # Topic für die GPIO Nr. des Lüfters

    def get_roomTemp(self): # Serverraumtemperatur aus der Cloud lesen
        self.__roomTemp = float((subscribe.simple(self.__topicRoomTemp, hostname=self.__hostname, retained=True)).payload)
        return self.__roomTemp
    def set_roomTemp(self, temp): # Serverraumtemperatur in Cloud schreiben (macht eigentlich nur Sinn, wenn auf diesem Raspi die Temperaturmessung stattfindet)
        publish.single(self.__topicRoomTemp, temp, hostname=self.__hostname, retain=True)
        return

    def get_setpointTemp(self): # Solltemperatur aus der Cloud lesen
        self.__setpointTemp = float((subscribe.simple(self.__topicSetpointTemp, hostname=self.__hostname, retained=True)).payload)
        return self.__setpointTemp
    def set_setpointTemp(self, setpointTemp): # Solltemperatur in die Cloud schreiben
        publish.single(self.__topicSetpointTemp, setpointTemp, hostname=self.__hostname, retain=True)
        return
        
    def get_hyst(self): # Hysterese aus der Cloud lesen
        self.__hyst = float((subscribe.simple(self.__topicHyst, hostname=self.__hostname, retained=True)).payload)
        return self.__hyst
    def set_hyst(self, hyst): # Hysterese in die Cloud schreiben
        publish.single(self.__topicHyst, hyst, hostname=self.__hostname, retain=True)
        return

    def get_gpioFan(self):
        self.__gpioFan = int((subscribe.simple(self.__topicGpioFan, hostname=self.__hostname, retained=True)).payload)
        return self.__gpioFan
    def set_gpioFan(self, gpioFan): # GPIO Kanal für Ventilator in die Cloud schreiben
        publish.single(self.__topicGpioFan, gpioFan, hostname=self.__hostname, retain=True)
        return

# ********************* Ende class Cloud
def main():
    mycloud=Cloud("localhost", "serverraum/1")
    mycloud.set_setpointTemp(26)
    mycloud.set_hyst(3)
    mycloud.set_gpioFan(18) # das ist auch der Pin für PWM

    zpr=Zpr(mycloud.get_setpointTemp(),mycloud.get_hyst()) # Sollwert und Hysterese
    fan=Fan(mycloud.get_gpioFan())
    tempsen1=Ds18b20("28-000006dccb21")

    while True:
        mycloud.set_roomTemp(tempsen1.get_celsius()) # aktuelle Temperatur in die Cloud schreiben
        print ("Raumtemp.: ", mycloud.get_roomTemp())
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
    
