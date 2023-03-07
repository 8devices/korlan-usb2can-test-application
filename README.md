# Korlan test application for Windows and Linux

A GUI application for basic "8 devices" Korlan USB2CAN operations testing over CAN bus. The program is implemented in Python and relies on a versatile [python-can](https://github.com/hardbyte/python-can) library. USB2CAN interface is used under Windows operating system and SocketCAN interface is used under Linux os.

## Installation for Windows

1. Install the Korlan USB2CAN driver. It can be downloaded from: https://www.8devices.com/media/products/usb2can_korlan/downloads/usb2can_winusb.msi.
2. Clone korlan-usb2can-test-application repository.
3. Install python 3.10: https://www.python.org/downloads/release/python-3105/.
4. Go to the cloned directory and install required python libraries with command `pip install -r requirements.txt`.
5. Python requires a CANAL DLL library for USB2CAN interface, which has to be put into the same directory as python files. It is provided in this repository.
6. Also, you will need to make some changes in *can.interfaces.usb2can.usb2canabstractionlayer* library, which was installed using pip with *python-can* package. Adjusted *usb2canabstractionlayer.py* file is provided in this repository.
7. Run the program using `py kcan.py` command.

## Installation for Linux (Ubuntu)

To set up an environment for kcan test application install python 3.9 using the following commands in the terminal:

```
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt install python3.9
```

After that, you will have to install needed libraries using the following commands:

```
sudo apt-get install python3-tk
sudo apt install python3-can
sudo apt install net-tools
sudo /bin/python3.9 -m pip install pysocketcan==0.0.2
sudo /bin/python3.9 -m pip install pillow==9.3.0
sudo /bin/python3.9 -m pip install matplotlib==3.6.2
sudo /bin/python3.9 -m pip install ttkbootstrap==1.10.1
```

Also, you will have to clone korlan-usb2can-test-application repository.
Then, you will need to go to the cloned directory and run the program using `sudo /bin/python3.9 kcan.py` command.
