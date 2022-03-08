import RPi.GPIO as GPIO
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe
import time

class Regelstrecke():
    def __init__(self, cloud, fan):
        self.__cloud=cloud # Konfigurationen und Werte
        self.__fan=fan # Der Aktor für den Zweipunktregler
        self.__splow=self.__cloud.get_setpointTemp() # untere Grenze
        self.__hyst=self.__cloud.get_hyst() #Hysterese speichern
        self.__sphigh=self.__splow+self.__hyst # obere Grenze

    def regeln(self):
        # Vergleich Ist- und Solltemperatur und Kühlung ansteuern
        # hier ist der Regler als Zweipunktregler mit Hysterese implementiert
        temperature = self.__cloud.get_roomTemp() # Aktuelle Temperatur aus der Cloud lesen

        if temperature <= self.__splow:
            self.__fan.off() # Kühlung ausschalten, wenn es kalt ist
        elif temperature > self.__sphigh:
            self.__fan.on() # Kühlung einschalten, wenn es zu warm wird
        return

# ********************* Ende class Regelstrecke

class Fan():
    def __init__(self, gpio):
        self.__gpio = gpio # GPIO Nr. des Lüfters
        GPIO.setmode(GPIO.BCM) # mit GPIO Bezeichnungen arbeiten
        GPIO.setup(self.__gpio, GPIO.OUT) # Fan GPIO als Ausgang schalten
        self.off() # Lüfter per default ausschalten
        self.__state = False # Zustand merken für Debuggingzwecke (siehe main())

    def on(self):
        GPIO.output(self.__gpio, 1) # GPIO.HIGH, Lüfter an
        self.__state = True # Zustand merken
        return

    def off(self):
        GPIO.output(self.__gpio, 0) # GPIO.LOW, Lüfter aus
        self.__state = False # Zustand merken
        return

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
    def __init__(self, hostname, basetopic, tempsen):
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
        self.__tempsen=tempsen # Der benutzte Temperatursensor

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

    def update(self): # Hier steht erstmal nur die Raumtemp., es können aber weitere Parameter zur Aktualisierung eingebaut werden
        temp = self.__tempsen.get_celsius()
        self.__roomTemp = temp
        self.__set_roomTemp(temp)
        return

# ********************* Ende class Cloud
def main():
    tempsen1=Ds18b20("28-000006dccb21")
    mycloud=Cloud("localhost", "serverraum/1", tempsen1) # URL des MQTT-Brokers, Basistopic und Quelle für Raumtemperatur
    mycloud.set_setpointTemp(26) # Unterer Schaltpunkt des Reglers
    mycloud.set_hyst(3) # Hysterese des Reglers
    mycloud.set_gpioFan(18) # Pin 18 ermöglicht optional PWM

    myfan=Fan(mycloud.get_gpioFan()) # Erste Abfrage in die Cloud
    raumklima=Regelstrecke (mycloud, myfan) # Speicherort für Sensorwerte und Aktor
 
    while True:
        mycloud.update() # aktuelle Temperatur (usw.) in die Cloud schreiben
        raumklima.regeln()
        print ("Raumtemp.: ", mycloud.get_roomTemp())
        temp=float(mycloud.get_roomTemp())
        if (myfan.get_state()==True):
            print ("Fan ist an")
        else:
            print ("Fan ist aus")
    return
 
# ********************* Ende Funktion main()

#  ********************* Hauptprogramm
if __name__ == '__main__':
    main()
    
