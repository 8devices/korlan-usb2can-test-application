import string, sys
import tkinter as tk
from tkinter import DISABLED, ttk
from tkinter.font import NORMAL
import korlan, threading, queue 
import can
import time
if korlan.OS == 'Windows':
    from can.interfaces.usb2can.usb2canabstractionlayer import CanalStatistics, CanalStatus
    from ctypes import byref
if korlan.OS == 'Linux':
    import time
class MainGUI:
    __WHITE = '#FFFFFF'
    __BG_GREY = '#DADADA'
    __FG_GREY = '#EEEEEE'
    __FONT = ("Lucida", 9)

    def __init__(self):
        self.can_datarate_tmp = 0
        self.can_datarate = 0
        self.korlan_ids = None
        self.can_id_tmp = ''
        self.can_id = ''
        self.stop_rx_thread = False
        self.can_rx_thread = False
        self.my_tree = None
        self.rx_by_id = False
        self.unique_id_tree = None
        self.unique_id_list = []
        self.unique_id_count = []
        self.que = queue.Queue()
        self.bus = None
        self.rx_frames = 0
        self.tx_frames = 0 
        self.rx_bytes  = 0
        self.tx_bytes  = 0
        self.bus_overr = 0
        self.bus_warnings = 0 
        self.bus_off = 0
        self.msg_count = 0
        self.waiting_for_device = True
        self.exit_flag = False
        if korlan.OS == 'Linux':
            self.rx_frames_count_starting_point = 0
            self.tx_frames_count_starting_point = 0
            self.rx_bytes_count_starting_point  = 0
            self.tx_bytes_count_starting_point  = 0
            self.bus_overr_count_starting_point = 0
            self.start_timestamp = 0
        self.__main_frame_creator()
        self.__tabs_creator()
        self.__status_bar()
    
    def __del__(self):
        if korlan.OS == 'Windows' and self.bus != None:
                self.bus.shutdown()

    def __main_frame_creator(self):
        self.root = tk.Tk()
        self.root.geometry("1000x550+270+180")
        self.root.resizable(width=False, height=False)
        self.root.title('Korlan - USB to CAN adapter test')  
        def __on_delete():
            if self.waiting_for_device == True:
                self.exit_flag = True
                self.bt_var.set(0)
            if self.can_rx_thread:
                self.stop_rx_thread = True
                self.can_rx_thread.join()
            self.root.destroy()
            sys.exit(0)
        self.root.protocol("WM_DELETE_WINDOW", __on_delete) #lambda: os._exit(0))
        if korlan.OS == 'Windows':
            self.root.iconbitmap('./8_devices_icon.ico')

    def __tabs_creator(self):
        style = ttk.Style()
        style.theme_create('st', settings={
            ".": {
                "configure": {
                    "background": self.__BG_GREY,
                    "font": self.__FONT
                }
            },
            "TNotebook": {
                "configure": {
                    "tabmargins": [2, 5, 0, 0],
                }
            },
            "TNotebook.Tab": {
                "configure": {
                    "padding": [10, 2]
                },
                "map": {
                    "background": [("selected", self.__FG_GREY)],
                    "expand": [("selected", [1, 1, 1, 0])]
                }
            }
        })
        style.theme_use('st')

        tab_control = ttk.Notebook(self.root)

        tab1 = ttk.Frame(tab_control)
        tab_control.add(tab1, text='Korlan')
        self.__tab1_content(tab1)

        tab2 = ttk.Frame(tab_control)
        tab_control.add(tab2, text='TX/RX')
        self.__tab2_content(tab2)

        tab_control.place(x=0, y=0, width=1000, height=558)

    def __tab2_content(self, tab_name):
        style = ttk.Style()  # Add some style
        style.theme_use("default")  # Pick a theme
        # Configure our treeview colors
        style.configure("Treeview", 
            background="#D3D3D3",
            foreground="black",
            rowheight=25,
            fieldbackground="#D3D3D3"
            )
        # Change selected color
        style.map('Treeview', 
            background=[('selected', 'blue')])

        # Create Treeview Frame
        tree_frame = ttk.Frame(tab_name)
        tree_frame.pack(padx = 20, pady=15, side = tk.TOP, anchor=tk.NW)

        # Treeview Scrollbar
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill = tk.Y)

        # Create Treeview
        self.my_tree = ttk.Treeview(tree_frame, yscrollcommand=tree_scroll.set,  height = 18)

        #Configure the scrollbar
        tree_scroll.config(command=self.my_tree.yview)

        # Define Our Columns 
        self.my_tree['columns'] = ("Counter","T_R","Time","Flags","CAN_ID","Len","Data")

        # Formate Our Columns
        self.my_tree.column("#0", width=0, stretch=tk.NO)
        self.my_tree.column("Counter", anchor=tk.CENTER, width=65)
        self.my_tree.column("T_R", anchor=tk.CENTER, width=35)
        self.my_tree.column("Time", anchor=tk.CENTER, width=80)
        self.my_tree.column("Flags", anchor=tk.CENTER, width=45)
        self.my_tree.column("CAN_ID", anchor=tk.CENTER, width=80)
        self.my_tree.column("Len", anchor=tk.CENTER, width=40)
        self.my_tree.column("Data", anchor=tk.CENTER, width=170)

        # Create Headings 
        self.my_tree.heading("#0", text="", anchor=tk.W)
        self.my_tree.heading("Counter", text="Counter", anchor=tk.CENTER)
        self.my_tree.heading("T_R", text="T/r", anchor=tk.CENTER)
        self.my_tree.heading("Time", text="Time (s)", anchor=tk.CENTER)
        self.my_tree.heading("Flags", text="Flags", anchor=tk.CENTER)
        self.my_tree.heading("CAN_ID", text="CAN ID", anchor=tk.CENTER)
        self.my_tree.heading("Len", text="DLC", anchor=tk.CENTER)
        self.my_tree.heading("Data", text="Data (hex)", anchor=tk.CENTER)

        self.my_tree.tag_configure('oddrow', background="white")
        self.my_tree.tag_configure('evenrow', background="lightblue")
        # Pack to the screen
        self.my_tree.pack(expand=1)

        # TX msg section
        # Create an entry widget for CAN ID.
        tk.Label(tab_name, text='CAN ID (hex):', background=self.__BG_GREY,
                font=self.__FONT, anchor='nw').place(x=570, y=15, width=80, height=25)
        self.msg_can_id = tk.StringVar()
        self.msg_can_id.set('1FFFFFFF')
        val_hex_cb = self.root.register(self.val_hex)  # Register callback function to variable
        # Callback function will be called to validate the input whenever any keystroke changes the widget’s contents.
        ttk.Entry(tab_name, textvariable=self.msg_can_id, validate="key", validatecommand=(val_hex_cb,'%P','%d')).place(x=570, y=35, width=80, height=20)

        # Create an entry widget for DATA.
        tk.Label(tab_name, text='DATA (hex):', background=self.__BG_GREY,
                font=self.__FONT, anchor='nw').place(x=725, y=15, width=100, height=25)
        self.msg_can_data = tk.StringVar()
        self.msg_can_data.set('0001020304050607')
        # Callback function will be called to validate the input whenever any keystroke changes the widget’s contents.
        ttk.Entry(tab_name, textvariable=self.msg_can_data, validate="key", validatecommand=(val_hex_cb,'%P','%d')).place(x=700, y=35, width=135, height=20)

        # Create a checkbutton windget for Extended Frame.
        self.msg_can_ext_frame = tk.StringVar()
        self.msg_can_ext_frame.set('1')
        tk.Checkbutton(tab_name,text="Extended Frame",variable=self.msg_can_ext_frame,onvalue=1,offvalue=0,height=2,width=15,anchor='w',
            background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT).place(x=850,y=25)
        
        # Send Data button
        self.tx_controll = tk.Button(tab_name, text='Send', justify=tk.CENTER, font=self.__FONT,
              command=self.__tx_bt, state=NORMAL)
        self.tx_controll.place(x=855, y=76, width=110, height=30)

        # Device statistics display    
        self.stats_var = tk.StringVar(tab_name)
        self.stats_var.set("No device stats available.")
        self.stats_details = tk.Label(tab_name, textvariable=self.stats_var, background=self.__BG_GREY,
        font=self.__FONT, anchor='nw', justify='left').place(x=600, y=180, width=420, height=150)
        
        # Clear device statistics button
        self.clear_st_bt = tk.Button(tab_name, text='Clear stats', justify=tk.CENTER, font=self.__FONT,
              command=self.__clear_stats).place(x=855, y=350, width=110, height=30)
        # Clear messages button
        self.clear_msg_bt = tk.Button(tab_name, text='Clear messages', justify=tk.CENTER, font=self.__FONT,
              command=self.__clear_msg).place(x=855, y=435, width=110, height=30)

    def __tab1_content(self, tab_name):
        # Window display, when no usb2can converter attached.
        button = tk.Button(self.root, text="Continue", width=40, command=lambda: self.bt_var.set(1))
        label = tk.Label(self.root, text='No Korlan attached to USB.\nPlease attach and click <Continue>.', #background=self.__BG_GREY,
                font=self.__FONT, anchor='ne')
        self.bt_var = tk.IntVar()
        while True:
            self.korlan_ids = korlan.get_usb_ids()
            if self.korlan_ids or self.exit_flag:
                break
            label.place(relx=.48, rely=.3, anchor="c", width=250, height=50)
            button.place(relx=.5, rely=.5, anchor="c")
            button.wait_variable(self.bt_var)
        self.waiting_for_device = False
        if self.exit_flag:
            sys.exit(0)
        if korlan.OS == 'Linux':
            self.start_timestamp = round(time.time(), 3)
        button.place_forget()
        label.place_forget()

        # Show device details.
        status_section = tk.LabelFrame(tab_name, text='Device details', background=self.__BG_GREY, font=self.__FONT)
        status_section.place(x=10, y=200, width=980, height=200)
        self.details_var = tk.StringVar(status_section)
        self.details_var.set("No device details available.")
        self.device_details = tk.Label(status_section, textvariable=self.details_var, background=self.__BG_GREY,
            font=self.__FONT, anchor='nw', justify='left').place(x=170, y=20, width=300, height=150)

        # Configure device.        
        config_section = tk.LabelFrame(tab_name, text='Configure', background=self.__BG_GREY, font=self.__FONT)
        config_section.place(x=10, y=15, width=980, height=200)

        # Select korlan device.
        tk.Label(config_section, text='Device ID:', background=self.__BG_GREY,
        font=self.__FONT, anchor='nw').place(x=170, y=15, width=65, height=25)
        self.korlan_id_text = tk.StringVar(config_section)
        if korlan.OS == 'Windows':  # Under windows korlan ids are stored in a list.
            self.korlan_id_text.set(self.korlan_ids[0])
            self.can_id_tmp = self.korlan_ids[0]  # Korlan id is saved to temporary variable at first. Only after config button is clicked changes will be in effect.
            id_entry = tk.OptionMenu(config_section, self.korlan_id_text, *self.korlan_ids, command=self.__id_changed)
        elif korlan.OS == 'Linux':  # Under linux korlan ids are stored in a dictionary.
            self.korlan_id_text.set(list(self.korlan_ids.keys())[0]) 
            self.can_id_tmp = self.korlan_ids[self.korlan_id_text.get()]
            id_entry = tk.OptionMenu(config_section, self.korlan_id_text, *self.korlan_ids.keys(), command=self.__id_changed)
        id_entry.config(background=self.__BG_GREY, font=self.__FONT) 
        id_entry.place(x=290, y=15, width=100, height=25)

        # Select can bus bit rate:
        tk.Label(config_section, text='CAN bus bit rate:', background=self.__BG_GREY,
                font=self.__FONT, anchor='nw').place(x=550, y=15, width=105, height=25)
        self.bit_rate_text = tk.StringVar(config_section)
        self.bit_rate_text.set(korlan.bit_rates_menu[0])
        br_entry = tk.OptionMenu(config_section, self.bit_rate_text, *korlan.bit_rates_menu, command=self.__rate_changed) 
        br_entry.config(background=self.__BG_GREY, font=self.__FONT) 
        br_entry.place(x=690, y=15, width=100, height=25)

        # Select can bus interface parameters
        if korlan.OS == 'Windows':  # Under windows USB2CAN interace
            self.loopback = tk.IntVar()
            self.silent = tk.IntVar()
            self.dis_auto_retr = tk.IntVar() 
            tk.Checkbutton(config_section,text="Loopback",variable=self.loopback,onvalue=2,offvalue=0,height=1,width=10,
                background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT, anchor='nw').place(x=170,y=60)
            tk.Checkbutton(config_section,text="Silent",variable=self.silent,onvalue=1,offvalue=0,height=1,width=10,
                background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT, anchor='nw').place(x=170,y=100)
            tk.Checkbutton(config_section,text="Disable auto retry",variable=self.dis_auto_retr,onvalue=4,offvalue=0,height=1,width=15,
                background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT, anchor='nw').place(x=330,y=60)


        if korlan.OS == 'Linux':  # Under linux SocketCAN interface
            self.local_loopback = tk.BooleanVar() 
            self.receive_own_messages = tk.BooleanVar()
            tk.Checkbutton(config_section,text="Local Loopback",variable=self.local_loopback,onvalue=True,offvalue=False,height=1,width=20,
                background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT, anchor='nw').place(x=160,y=70)
            tk.Checkbutton(config_section,text="Receive Own Messages",variable=self.receive_own_messages,onvalue=True,offvalue=False,height=1,width=20,
                background=self.__BG_GREY,activebackground=self.__BG_GREY,font=self.__FONT, anchor='nw').place(x=160,y=110)
        tk.Button(config_section, text='Configure', justify=tk.CENTER, font=self.__FONT,
            command=self.__config_bt).place(x=690, y=95, width=100, height=30)

    if korlan.OS == 'Windows':
        # Under windows CANAL_API is used to get status and statistics.
        # CANAL_API specifications can be found here: https://www.8devices.com/media/products/usb2can_korlan/downloads/CANAL_API.pdf
        def __update_stats(self):
            status = CanalStatus()
            self.bus.can.get_status(self.bus.handle, byref(status))
            #print(status.channel_status, status.lasterrorcode, status.lasterrorsubcode,status.lasterrorstr)
            CANAL_STATUS_PASSIVE =  0x40000000
            CANAL_STATUS_BUS_OFF =  0x80000000
            CANAL_STATUS_BUS_WARN = 0x20000000
            self.bus_offline = self.bus_passive = self.bus_warning = False
            self.canal_status = 'Ok'
            if status.channel_status & CANAL_STATUS_BUS_OFF:
                self.bus_offline = True
                self.canal_status = "Bus offline"
            elif status.channel_status & CANAL_STATUS_PASSIVE:
                self.bus_passive = True
                self.canal_status = "Bus passive"
            elif status.channel_status & CANAL_STATUS_BUS_WARN:
                self.bus_warning = True
                self.canal_status = "Bus warning"
            self.rx_err = (status.channel_status >> 8) & 0xff
            self.tx_err = status.channel_status & 0xff

            statistics = CanalStatistics()
            self.bus.can.get_statistics(self.bus.handle, byref(statistics))
            self.rx_frames += statistics.ReceiveFrams
            self.tx_frames += statistics.TransmistFrams 
            self.rx_bytes  += statistics.ReceiveData
            self.tx_bytes  += statistics.TransmitData
            self.bus_overr += statistics.Overruns
            self.bus_warnings += statistics.BusWarnings 
            self.bus_off += statistics.BusOff
            s = f"RX frames:\t{self.rx_frames}\tTX frames:\t{self.tx_frames}\n\nRX bytes:\t\t{self.rx_bytes}\tTX bytes:\t\t{self.tx_bytes}\n\nBus overruns:\t{self.bus_overr}\tBus warnings:\t{self.bus_warnings}\n\nBus OFF's:\t{self.bus_off}\n\nCanal status:\t{self.canal_status}"
            self.stats_var.set(s)
            self.statusbar.config(text=
                f'   Korlan ID {self.can_id}: is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.\t\t\t\t\t\t\t\tRX err:{self.rx_err}   TX err:{self.tx_err}')
            self.root.after(1000, self.__update_stats)

    elif korlan.OS == 'Linux':
        def __update_stats(self):
            status = can.bus.BusState
            self.bus_state = ''
            if self.bus.state == status.ACTIVE:
                self.bus_state = 'Active'
            elif self.bus.state == status.ERROR:
                self.bus_state = 'Error'
            elif self.bus.state == status.PASSIVE:
                self.bus_state = 'Passive'

            self.rx_frames, self.rx_bytes, self.tx_frames, self.tx_bytes, self.bus_overr, self.rx_err, self.tx_err \
                = korlan.get_statistics(self.can_id, self.rx_frames_count_starting_point, self.rx_bytes_count_starting_point,
                                        self.tx_frames_count_starting_point, self.tx_bytes_count_starting_point, self.bus_overr_count_starting_point)
            s = f"RX frames:\t{self.rx_frames}\tTX frames:\t{self.tx_frames}\n\nRX bytes:\t\t{self.rx_bytes}\tTX bytes:\t\t{self.tx_bytes}\n\nBus overruns:\t{self.bus_overr}\n\nBus state:\t\t{self.bus_state}\t"
            self.stats_var.set(s)
            self.statusbar.config(text =
                f'   Korlan ID {list(self.korlan_ids.keys())[list(self.korlan_ids.values()).index(self.can_id)]}: is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.\t\t\t\t\t\tRX err: {self.rx_err}   TX err: {self.tx_err}')
            self.root.after(1000, self.__update_stats)

    def __clear_stats(self):
        if korlan.OS == 'Linux':
            self.rx_frames_count_starting_point, self.rx_bytes_count_starting_point, self.tx_frames_count_starting_point, \
            self.tx_bytes_count_starting_point, self.bus_overr_count_starting_point, self.rx_err, self.tx_err = korlan.get_raw_statistics(self.can_id)
        if korlan.OS == 'Windows':
            self.rx_frames = 0
            self.tx_frames = 0
            self.rx_bytes  = 0
            self.tx_bytes  = 0
            self.bus_overr = 0
            self.bus_warnings = 0
            self.bus_off = 0

    def __clear_msg(self):
        self.my_tree.delete(*self.my_tree.get_children())
        self.msg_count = 0
        
    def is_hex(self, s):
        hex_digits = set(string.hexdigits)
        # If s is long, then it is faster to check against a set
        return all(c in hex_digits for c in s)

    def val_hex(self, inStr,acttyp):
        if inStr == '':
            inStr = '0'
        if acttyp == '1':  # New character inserted
            if not self.is_hex(inStr):
                return False
        return True

    def __status_bar(self):
        self.statusbar = tk.Label(self.root, text="Not connected to Korlan device.", bd=1, anchor=tk.W, relief=tk.RAISED,
            background=self.__BG_GREY, font=self.__FONT)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    
    if korlan.OS == 'Windows':
        def __id_changed(self, *args):
            self.can_id_tmp = self.korlan_id_text.get()

    elif korlan.OS == 'Linux':
        def __id_changed(self, *args):
            self.can_id_tmp = self.korlan_ids[self.korlan_id_text.get()]

    def __rate_changed(self, *args):
        self.can_datarate_tmp = korlan.bit_rates_menu.index(self.bit_rate_text.get())

    def __config_bt(self):
        device_details_text=''
        self.can_datarate = self.can_datarate_tmp
        self.can_id = self.can_id_tmp
        self.stop_rx_thread = True  # Shutting down RX thread, so it would be restarted with new bus interface.
        time.sleep(0.5)
        # Create new can bus interface
        if korlan.OS == 'Windows':
            check_flags = self.loopback.get() | self.silent.get() | self.dis_auto_retr.get()
            #print('flags = ', bin(check_flags))
            self.bus, vendor_iter = korlan.get_bus(self.bus, id=self.can_id, rate=korlan.bit_rates[self.can_datarate] * 1000, bus_flags = check_flags)
            if check_flags == 1 or check_flags == 5:
                self.tx_controll.config(state=DISABLED)
            else:
                self.tx_controll.config(state=NORMAL)
            
        elif korlan.OS == 'Linux':
            self.bus, vendor_iter = korlan.get_bus(self.bus, id=self.can_id, new_rate=korlan.bit_rates[self.can_datarate] * 1000,
                                                   recv_own_msg=self.receive_own_messages.get(), loopback=self.local_loopback.get())
        # Show device details
        for e,v in vendor_iter:
            device_details_text += f'{e}:\t\t{v}\n'
        self.details_var.set(device_details_text)

        if korlan.OS == 'Windows':
            self.statusbar.config(text=
                f'   Korlan ID {self.can_id}: is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.')
        elif korlan.OS == 'Linux':
            self.statusbar.config(text=
                f'   Korlan ID {list(self.korlan_ids.keys())[list(self.korlan_ids.values()).index(self.can_id)]}: is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.')

        if not self.can_rx_thread:
            self.stop_rx_thread = False
            self.can_rx_thread = threading.Thread(target=korlan.rx_msgs, args=(self.bus, self.root, lambda : self.stop_rx_thread, self.que ),
                                                  daemon=True)
            self.root.bind('<<CAN_RX_event>>', self.__can_rxtx_show)
            self.can_rx_thread.start()
        else:
            self.can_rx_thread.join() # Stop can_rx_thread
            if not self.can_rx_thread.is_alive():
                self.stop_rx_thread = False
                self.can_rx_thread = threading.Thread(target=korlan.rx_msgs, args=(self.bus, self.root, lambda : self.stop_rx_thread, self.que ),
                                                      daemon=True) # Start new can_rx_thread with new can bus interface
                self.can_rx_thread.start()

        self.__clear_stats()
        self.rx_err = 0
        self.tx_err = 0
        self.__update_stats()

    def __can_rxtx_show(self,event):
        msgl = self.que.get()
        self.msg_count += 1
        dta = " ".join("{:02X}".format(c) for c in msgl[5])
        if korlan.OS == "Windows":
            time = msgl[1] / 1000
        elif korlan.OS == "Linux":
            if msgl[0] == 'r':
                time = msgl[1] - self.start_timestamp
            else:
                time = msgl[1]
        self.my_tree.insert(parent='', index='end', iid=self.msg_count, text="", 
            values=(
                self.msg_count,             # msg count during session
                msgl[0],                    # tx/rx
                f'{time:.3f}',      # time stamp
                msgl[2],                    # flags
                f'{msgl[3]:08X}',           # CAN ID
                msgl[4],                    # dlc
                dta  #f' {msgl[5].hex().upper()}' # data
            ),tags=('evenrow' if self.msg_count%2 else 'oddrow',) )
        self.my_tree.yview_moveto(1)        # show last received msg's

        # When messages count reaches 1000, delete 100 first rows to save memory
        rows_len = len(self.my_tree.get_children())
        if rows_len > 9999:
            del_msg_count = int(rows_len / 10)
            for row in self.my_tree.get_children():
                self.my_tree.delete(row)
                del_msg_count -= 1
                if del_msg_count == 0:
                    break
  
    def __tx_bt(self):
        id_s = self.msg_can_id.get()
        data = []
        input_data = self.msg_can_data.get()
        ext = self.msg_can_ext_frame.get()
        if ext == '1':
            is_extended_id = True
        else:
            is_extended_id = False
        for i in range(0, len(input_data), 2):
            data.append(int(input_data[i + 0 : i + 2], 16))
        korlan.tx_msg(self.bus, self.que, int(id_s, 16), data, is_extended_id)
        if not self.que.empty():
            self.__can_rxtx_show(None)

if korlan.OS == 'Windows' or 'Linux':
    MainGUI().root.mainloop()
else:
    print("The operating system is not supported by this application")
    