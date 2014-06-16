Setup instructions...

SIM Server
-------------------------

Running on RaspberryPI, implemented in Python

Dependencies:
- Secure card lib: Pyscard (+pcsc-lite)
- ZMQ: pyzmq 

Connect SmartCard reader (Gemalto PC Twin Reader in our case) to the RaspberryPI. *Important! Must be powered...* Current drawn from Pi's USB slot is insufficient to power the reader and the smartcard.

Install server script on the device:
	
	simserver.py

Also important to have set up all certificates properly:

	generate_certificates.py
	certificates/
	private_keys/server.key_secret
	public_keys/server.key
	public_keys/client.key

Setup cron to launch it after reboot:

	@reboot python /home/pi/simserver.py &


Command relay daemon
--------------------------

Same prerequisites as above, plus dbus support. The relay script listens for method calls on a dbus and relays all commands to the ZMQ socket to the server. The server's IP address is configured statically.

Install relay script:

	dbusrelaynet.py
	
Given previously setup private keys, they must be located as:

	certificates/
	private_keys/client.key_secret
	public_keys/server.key
	public_keys/client.key

Must also setup dbus rules to allow communication via specific dbus (*/etc/dbus-1/system.d/remoteSim-server.conf*):

	remoteSim-server.conf


Bluetooth SIM sharing
---------------------

Bluetooth option is very simple:

1. Pair the controller's (mac or raspberryPI) bluetooth with bluetooth-sap capable phone (galaxy s4)
2. Start ofonod from ofono-bt
3. Find the sap modem id using test/list-modems
4. Run test/enable-modem modem_id

If everything works corretly, that should be it.

WiFi SIM sharing
---------------------

The only differences for this option are:

1. Running ofonod from ofono-wifi
2. Having launched the SIM server on the same network
3. And having launched command relay daemon on the same machine (that talks to the SIM server)
4. Repeat the steps with list-modems and enable-modem


