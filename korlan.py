from tkinter import *
import subprocess
import can
import re
import platform

if platform.system() == 'Windows':
    OS = 'Windows'
elif platform.system() == "Linux":
    OS = 'Linux'

if OS == 'Windows':
    import win32com.client

    def get_usb_ids(usb_VIDPID = "VID_0483&PID_1234"): # Korlan VID_0483&PID_1234
        usb_ids = []
        wmi = win32com.client.GetObject ("winmgmts:")
        for usb in wmi.InstancesOf ("win32_usbcontrollerdevice"):
            if usb_VIDPID in usb.Dependent:
                usb_ids.append(usb.Dependent.split('\\\\')[-1][:-1])
        return usb_ids

   
    def get_bus(bus, id='D3365AFB', rate=1000000, bus_flags=0, dll_path='./usb2can.dll'):
        # vendor string example: '2.4;2.0;2.0.0;2.0.0;8devices.com'
        if bus != None:
            bus.shutdown()
        bus = can.interface.Bus(bustype="usb2can", channel=id, bitrate=rate, dll=dll_path, flags=bus_flags)
        try:
            vs_pointer = bus.can.get_vendor_string() # Function returns bytes type value (pointer to a vendor string). It needs to be decoded to string.
            #print(type(vs_pointer), vs_pointer)
            vendor_string = vs_pointer.decode()#.rstrip('\x00')
        except Exception as e:
            #print(f"Can't get vendor string. {e}")
            vendor_string = '2.x;2.x;2.x.x;2.x.x;8devices.com'
        vendor_list = vendor_string.replace(':', ';').split(';')
        explanation = ['Firmware version','Hardware version','Canal version','DLL version','Device vendor']
        return bus, zip(explanation, vendor_list)

elif OS == 'Linux':
    import pysocketcan as pysc
    def get_usb2can_devices():
        usb_devices_info = [] # Processed usb-devices data. 2D list.
        global usb2can_devices
        usb2can_devices = []

        usb_devices_string = str(subprocess.run(["usb-devices"], stdout=subprocess.PIPE))  # usb-devices command output.
        usb_devices_list = usb_devices_string.split(r'\n\n')  # usb-devices output devided to list, where one item describes one device.
        
        for block in usb_devices_list:
            new_block = []
            list_of_rows = re.split(r"[TDPSCI]:  ", block)  # Each device information block is devided into rows.
            list_of_rows = list(filter(None, list_of_rows))  # Remove empty strings from list.
            for row in list_of_rows:
                row = row.replace('\\n','')  # Remove unwanted symbols.
                new_block.append(row)
            usb_devices_info.append(new_block)
        usb_devices_info[0].pop(0)  # Remove irrelevant string.

        for block in usb_devices_info:  # Find usb2can devices
            if "Product=USB2CAN converter" in block[4]:  # Fifth row of usb device's information block
                usb2can_devices.append(block)

    def get_usb_ids():
        get_usb2can_devices()
        usb2can_ids = {}  # Dictionary that this function returns. Key - korlan's serial number. Value - socketcan interface (can0; can1; etc.).
        i = 0
        for korlan in usb2can_devices:
            usb2can_ids[korlan[5].split("SerialNumber=", 1)[1]] = 'can' + str(i)
            i = i + 1
        return usb2can_ids

    def get_bus(bus, id='can0', new_rate=1000000, recv_own_msg=False, loopback=True):
        if bus != None:
            bus.shutdown()
        if "DOWN" in str(subprocess.run(['ip', 'addr', 'ls', 'dev', id], stdout=subprocess.PIPE)):
            current_rate = 0
        else:
            current_rate = pysc.Interface(id).baud
        if int(current_rate) != new_rate:
            subprocess.run(['ip',  'link',  'set',  'down', id])
            subprocess.run(['ip', 'link', 'set', id, 'type', 'can', 'bitrate', str(new_rate)])
            subprocess.run(['ip', 'link', 'set', 'up', id])
        bus = can.interface.Bus(
            interface="socketcan", channel=id, receive_own_messages=recv_own_msg,
            local_loopback=loopback) # Create socketcan bus interface
        vendor_list = []
        try:
            device = int(id.split('can', 1)[1]) 
            vendor_list.append(usb2can_devices[device][1].split(' ')[1]) # Get hardware version
            vendor_list.append(usb2can_devices[device][3].split('Manufacturer=', 1)[1]) # Get manufacturer
        except Exception as e:
            # print(f"Can't get vendor string. {e}")
            vendor_list = ['2.x', '8devices.com']
        explanation = ['Hardware version', 'Manufacturer']
        return bus, zip(explanation, vendor_list)


    def get_raw_statistics(can_id):
        # Raw statistics is taken with bash command
        can_interface_statistics_string = str(subprocess.run(['ifconfig', can_id], stdout=subprocess.PIPE))

        rx_frames = int(can_interface_statistics_string.split('RX packets')[1].split()[0])
        rx_bytes = int(can_interface_statistics_string.split('bytes')[1].split()[0])
        tx_frames = int(can_interface_statistics_string.split('TX packets')[1].split()[0])
        tx_bytes = int(can_interface_statistics_string.split('bytes')[2].split()[0])
        bus_overr = int(can_interface_statistics_string.split('overruns')[1].split()[0]) + int(can_interface_statistics_string.split('overruns')[2].split()[0])
        rx_err = int(can_interface_statistics_string.split('RX errors')[1].split()[0])
        tx_err = int(can_interface_statistics_string.split('TX errors')[1].split()[0])

        return rx_frames, rx_bytes, tx_frames, tx_bytes, bus_overr, rx_err, tx_err


    def get_statistics(can_id, rx_frames_count_starting_point, rx_bytes_count_starting_point,
                       tx_frames_count_starting_point, tx_bytes_count_starting_point, bus_overr_count_starting_point):
        # Bash command shows total connection time statistics.
        # If user wants to reset statistics, it has to be counted from the new, last marked, point.
        rx_frames_raw, rx_bytes_raw, tx_frames_raw, tx_bytes_raw, bus_overr_raw, rx_err, tx_err = get_raw_statistics(can_id)
        rx_frames = rx_frames_raw - rx_frames_count_starting_point
        rx_bytes = rx_bytes_raw - rx_bytes_count_starting_point
        tx_frames = tx_frames_raw - tx_frames_count_starting_point
        tx_bytes = tx_bytes_raw - tx_bytes_count_starting_point
        bus_overr = bus_overr_raw - bus_overr_count_starting_point

        return rx_frames, rx_bytes, tx_frames, tx_bytes, bus_overr, rx_err, tx_err

bit_rates = [1000,800,500,250,125,62.5,20,10]
bit_rates_menu = [f'{x} kbit/s' for x in bit_rates]

def rx_msgs(bus, main_thread, stop, q):
    try:
        # print("RX startup")
        while True:
            if stop():
                # print('RX shutdown')
                break
            msgl=[]
            msg = bus.recv(0.5)
            if msg is not None:
                if msg.is_error_frame:
                    continue
                msg_flags = f"{'X' if msg.is_extended_id else '.'}{'R' if msg.is_remote_frame else '.'}{'E' if msg.is_error_frame else '.'}"
                #print('msgflag:',msg_flags)    
                msgl.append('r')    #RX msg
                msgl.append(msg.timestamp)
                msgl.append(msg_flags)
                msgl.append(msg.arbitration_id)
                msgl.append(msg.dlc)
                msgl.append(msg.data)
                q.put(msgl)
                main_thread.event_generate('<<CAN_RX_event>>', when='tail') # Generate event so that received message would be shown in a Treeview
    except Exception as e:
        print(f"Korlan RX exception {e}",e)

    pass  # exit normally

def tx_msg(bus, q, id, rem_data, ext_id):
    #with can.ThreadSafeBus(bustype="usb2can", channel=id, bitrate = bit_rates[brate]*1000, dll='./usb2can.dll') as bus:
    try:
        msg = can.Message(arbitration_id = id, data=rem_data, is_extended_id=ext_id)
        bus.send(msg,0.5)
        #print(f"Message sent on{t} {bus.channel_info}\n{msg}")
        msgl=[]
        msg_flags = f"{'X' if msg.is_extended_id else '.'}{'R' if msg.is_remote_frame else '.'}{'E' if msg.is_error_frame else '.'}"
        msgl.append('T')    #TX msg
        msgl.append(msg.timestamp)
        msgl.append(msg_flags)
        msgl.append(msg.arbitration_id)
        msgl.append(msg.dlc)
        msgl.append(msg.data)
        q.put(msgl)
    except can.CanError:
        print("Message NOT sent")
        
