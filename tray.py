
TRAY_DIR_PIN = 10
TRAY_STEP_PIN = 8

GPIO.setup(TRAY_DIR_PIN, GPIO.OUT)
GPIO.setup(TRAY_STEP_PIN, GPIO.OUT)
GPIO.output(TRAY_DIR_PIN, 1)

try:
	while True:
		sleep(1.0)
		GPIO.output(TRAY_DIR_PIN,1)  # CW

		for x in range(200):
			GPIO.output(TRAY_STEP_PIN,GPIO.HIGH)
			sleep(.005)
			GPIO.output(TRAY_STEP_PIN,GPIO.LOW)
			sleep(.005)

 		sleep(1.0)
		GPIO.output(TRAY_DIR_PIN,0)  # CCW

		for x in range(200):
			GPIO.output(TRAY_STEP_PIN,GPIO.HIGH)
			sleep(.005)
			GPIO.output(TRAY_STEP_PIN,GPIO.LOW)
			sleep(.005)

except KeyboardInterrupt:
	print("cleanup")
	GPIO.cleanup()