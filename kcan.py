import string
import sys
import tkinter as tk
from tkinter import DISABLED, ttk, messagebox
from tkinter.font import NORMAL
import time

import threading
import queue
from functools import partial
import collections

import can
import ttkbootstrap as tb
from ttkbootstrap import Style
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import korlan

if korlan.OS == 'Windows':
    from ctypes import byref
    from can.interfaces.usb2can.usb2canabstractionlayer import CanalStatistics, CanalStatus


# For a list of PIDs visit https://en.wikipedia.org/wiki/OBD-II_PIDs
ENGINE_COOLANT_TEMP = 0x05
ENGINE_RPM = 0x0C
VEHICLE_SPEED = 0x0D
MAF_SENSOR = 0x10
O2_VOLTAGE = 0x14
THROTTLE = 0x11
FUEL_TANK_LEVEL = 0x2F
EVAP_SYSTEM_VAPOR_PRESSURE = 0x32
ENGINE_OIL_TEMP = 0x5C
ACCELERATOR_PEDAL_POSITION = 0x49

PID_REQUEST = 0x7DF
PID_REPLY = 0x7E8


class MainGUI:
    _WHITE = '#FFFFFF'
    _BG_GREY = '#DADADA'
    _FG_GREY = '#EEEEEE'
    _FONT = ("Lucida", 9)
    _FONT_BIG = ("Lucida", 20)

    def __init__(self):
        self.can_datarate_tmp = 0
        self.can_datarate = 0
        self.korlan_ids = None
        self.can_id_tmp = ''
        self.can_id = ''
        self.stop_rx_thread = False
        self.can_rx_thread = None
        self.stop_obdii_tx_thread = False
        self.can_obdii_tx_thread = None
        self.my_tree = None
        self.rx_by_id = False
        self.unique_id_tree = None
        self.unique_id_list = []
        self.unique_id_count = []
        self.que = queue.Queue()
        self.bus = None
        self.rx_frames = 0
        self.tx_frames = 0
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.bus_overr = 0
        self.bus_warnings = 0
        self.bus_off = 0
        self.msg_count = 0
        self.waiting_for_device = True
        self.exit_flag = False
        self.tx_can_id_length = 8
        self.filter_can_id_length = [8, 8, 8, 8]
        self.filter_is_extended_id = []
        self.obdii_tab3_sensor_list = []
        self.obdii_diagrams_data_list = []
        self.tab3_parameter_count = 0
        self.tab4_parameter_count = 0
        if korlan.OS == 'Linux':
            self.rx_frames_count_starting_point = 0
            self.tx_frames_count_starting_point = 0
            self.rx_bytes_count_starting_point = 0
            self.tx_bytes_count_starting_point = 0
            self.bus_overr_count_starting_point = 0
            self.start_timestamp = 0
        self._main_frame_creator()
        self._tabs_creator()
        self._status_bar()
        self.temperature_value = tk.StringVar(value="-")
        self.engine_rpm_value = tk.StringVar(value="-")
        self.vehicle_speed_value = tk.StringVar(value="-")
        self.maf_sensor_value = tk.StringVar(value="-")
        self.o2_voltage_value = tk.StringVar(value="-")
        self.throttle_position_value = tk.StringVar(value="-")
        self.evap_system_pressure_value = tk.StringVar(value="-")
        self.engine_oil_temp_value = tk.StringVar(value="-")
        self.accelerator_position_value = tk.StringVar(value="-")

    def __del__(self):
        if korlan.OS == 'Windows' and self.bus is not None:
            self.bus.shutdown()

    def _on_delete(self):
        if self.waiting_for_device:
            self.exit_flag = True
            self.bt_var.set(0)
        if self.can_rx_thread:
            self.stop_rx_thread = True
            self.can_rx_thread.join(2)
        if self.can_obdii_tx_thread:
            self.stop_obdii_tx_thread = True
            self.can_obdii_tx_thread.join(2)
        self.root.destroy()
        sys.exit(0)

    def _main_frame_creator(self):
        self.root = tk.Tk()
        self.root.geometry("1000x550+270+180")
        self.root.resizable(width=False, height=False)
        self.root.title('Korlan - USB to CAN adapter test')
        if korlan.OS == 'Windows':
            self.root.iconbitmap('./8_devices_icon.ico')
        self.root.protocol("WM_DELETE_WINDOW", self._on_delete)  # lambda: os._exit(0))

    def _tabs_creator(self):
        Style(theme="superhero")

        tab_control = ttk.Notebook(self.root)

        tab1 = ttk.Frame(tab_control)
        tab_control.add(tab1, text='Korlan')
        self._tab1_content(tab1)

        tab2 = ttk.Frame(tab_control)
        tab_control.add(tab2, text='TX/RX')
        self._tab2_content(tab2)

        self.tab3 = ttk.Frame(tab_control)
        self.tab3.grid()
        tab_control.add(self.tab3, text='OBD2')
        self._tab3_content(self.tab3)

        self.tab4 = ttk.Frame(tab_control)
        tab_control.add(self.tab4, text="OBD2 diagrams")
        self._tab4_content(self.tab4)

        tab_control.place(x=0, y=0, width=1000, height=558)

    def _tab1_content(self, tab_name):
        # Window display, when no usb2can converter attached.
        button = ttk.Button(self.root, text="Continue", width=40, command=lambda: self.bt_var.set(1))
        label = ttk.Label(self.root, text='No Korlan attached to USB.\nPlease attach and click <Continue>.',
                          font=self._FONT, justify='center', anchor='center')
        self.bt_var = tk.IntVar()
        while True:
            self.korlan_ids = korlan.get_usb_ids()
            if self.korlan_ids or self.exit_flag:
                break
            label.place(relx=.5, rely=.35, anchor="center", width=250, height=50)
            button.place(relx=.5, rely=.5, anchor="center")
            button.wait_variable(self.bt_var)
        self.waiting_for_device = False
        if self.exit_flag:
            sys.exit(0)
        if korlan.OS == 'Linux':
            self.start_timestamp = round(time.time(), 3)
        button.place_forget()
        label.place_forget()

        # Show device details.
        status_section = ttk.LabelFrame(tab_name, text='Device details')
        status_section.place(x=10, y=200, width=980, height=200)
        self.details_var = tk.StringVar(status_section)
        self.details_var.set("No device details available.")
        ttk.Label(status_section, textvariable=self.details_var, font=self._FONT,
                  anchor='nw', justify='left').place(x=170, y=20, width=300, height=150)

        # Configure device.
        config_section = ttk.LabelFrame(tab_name, text='Configure')
        config_section.place(x=10, y=15, width=980, height=200)

        # Select korlan device.
        ttk.Label(config_section, text='Device ID:', font=self._FONT,
                   anchor='nw').place(x=40, y=15, width=70, height=25)
        self.korlan_id_text = tk.StringVar(config_section)
        if korlan.OS == 'Windows':  # Under windows korlan ids are stored in a list.
            self.korlan_id_text.set(self.korlan_ids[0])
            # Korlan id is saved to temporary variable at first.
            # Only after config button is clicked changes will be in effect.
            self.can_id_tmp = self.korlan_ids[0]
            id_entry = tb.Menubutton(config_section, textvariable=self.korlan_id_text)
            menu = tk.Menu(id_entry)
            for korlan_id in self.korlan_ids:
                menu.add_radiobutton(
                    label=korlan_id,
                    value=korlan_id,
                    variable=self.korlan_id_text,
                    command=self._id_changed
                )
            id_entry["menu"] = menu

        elif korlan.OS == 'Linux':  # Under linux korlan ids are stored in a dictionary.
            self.korlan_id_text.set(list(self.korlan_ids.keys())[0])
            self.can_id_tmp = self.korlan_ids[self.korlan_id_text.get()]
            id_entry = tb.Menubutton(config_section, textvariable=self.korlan_id_text)
            menu = tk.Menu(id_entry)
            for korlan_id in self.korlan_ids.keys():
                menu.add_radiobutton(
                    label=korlan_id,
                    value=korlan_id,
                    variable=self.korlan_id_text,
                    command=self._id_changed
                )
            id_entry["menu"] = menu
        id_entry.place(x=170, y=15, width=100)

        # Select can bus bit rate:
        ttk.Label(config_section, text='CAN bus bit rate:',
                  font=self._FONT, anchor='nw').place(x=40, y=50, width=115, height=25)
        self.bit_rate_text = tk.StringVar(config_section)
        self.bit_rate_text.set(korlan.bit_rates_menu[0])

        br_entry = tb.Menubutton(config_section, textvariable=self.bit_rate_text)
        menu = tk.Menu(br_entry)
        for bit_rate in korlan.bit_rates_menu:
            menu.add_radiobutton(
                label=bit_rate,
                value=bit_rate,
                variable=self.bit_rate_text,
                command=self._rate_changed
            )
        br_entry["menu"] = menu
        #
        # br_entry = tk.OptionMenu(config_section, self.bit_rate_text, *korlan.bit_rates_menu,
        #                          command=self._rate_changed)
        br_entry.place(x=170, y=50, width=100)

        # Select can bus interface parameters
        if korlan.OS == 'Windows':  # Under windows USB2CAN interace
            self.loopback = tk.IntVar()
            self.silent = tk.IntVar()
            self.dis_auto_retr = tk.IntVar()
            self.obdii_tab = tk.BooleanVar()
            ttk.Checkbutton(config_section, text="Loopback", variable=self.loopback, onvalue=2,
                            offvalue=0, bootstyle="info", width=10, command=self._chk).place(x=40, y=100)
            ttk.Checkbutton(config_section, text="Silent", variable=self.silent, onvalue=1, offvalue=0,
                            bootstyle="info", width=10, command=self._chk).place(x=40, y=130)
            ttk.Checkbutton(config_section, text="Disable auto retry", variable=self.dis_auto_retr, onvalue=4,
                            bootstyle="info", offvalue=0, width=16).place(x=150, y=100)
            self.obdii_checkbox = ttk.Checkbutton(config_section, text="OBD2", variable=self.obdii_tab, onvalue=True, 
                                                  bootstyle="info", offvalue=False, width=15)
            self.obdii_checkbox.place(x=150, y=130)

        if korlan.OS == 'Linux':  # Under linux SocketCAN interface
            self.loopback = tk.BooleanVar()
            self.silent = tk.BooleanVar()
            self.dis_auto_retr = tk.BooleanVar()
            self.obdii_tab = tk.BooleanVar()
            ttk.Checkbutton(config_section, text="Loopback", variable=self.loopback, onvalue=True, offvalue=False,
                            bootstyle="info", width=10, command=self._chk).place(x=40, y=100)
            ttk.Checkbutton(config_section, text="Silent", variable=self.silent, onvalue=True, offvalue=False,
                            bootstyle="info", width=10, command=self._chk).place(x=40, y=130)
            ttk.Checkbutton(config_section, text="Disable auto retry", variable=self.dis_auto_retr,
                            bootstyle="info", onvalue=True, offvalue=False, width=15).place(x=150, y=100)
            self.obdii_checkbox = ttk.Checkbutton(config_section, text="OBD2", variable=self.obdii_tab,
                                                  bootstyle="info", onvalue=True, offvalue=False, width=15)
            self.obdii_checkbox.place(x=150, y=130)

        # FILTERING
        ttk.Label(config_section, text='RX filtering:',
                  font=self._FONT, anchor='nw').place(x=340, y=15, width=85, height=25)

        # Create an entry widget for CAN ID (hex)
        ttk.Label(config_section, text='CAN ID (hex):',
                  font=self._FONT, anchor='nw').place(x=442, y=15, width=95, height=25)
        self.filter_msg_can_ids = [tk.StringVar() for _ in range(4)]
        self.entry_filter_msg_can_ids = [ttk.Entry() for _ in range(4)]
        val_hex_cb = self.root.register(self.val_hex_len)  # Register callback function to variable
        position_y = 40
        for i in range(4):
            # Callback function will be called to validate the input
            # whenever any keystroke changes the widget’s contents.
            self.entry_filter_msg_can_ids[i] = ttk.Entry(config_section, textvariable=self.filter_msg_can_ids[i],
                                                         validate="key", validatecommand=(val_hex_cb, '%P', '%d', None,
                                                                                          True, i))
            self.entry_filter_msg_can_ids[i].place(x=445, y=position_y, width=80, height=25)
            position_y += 35

        # Create an entry widget for CAN MASK (hex).
        ttk.Label(config_section, text='CAN MASK (hex):',
                  font=self._FONT, anchor='nw').place(x=542, y=15, width=115, height=25)

        self.filter_can_masks = [tk.StringVar() for _ in range(4)]
        position_y = 40
        for i in range(4):
            # Callback function will be called to validate the input
            # whenever any keystroke changes the widget’s contents.
            ttk.Entry(config_section, textvariable=self.filter_can_masks[i], validate="key",
                      validatecommand=(val_hex_cb, '%P', '%d', 8)).place(x=560, y=position_y, width=80, height=25)
            position_y += 35

            # Is extended id
        ttk.Label(config_section, text='Extended ID:',
                  font=self._FONT, anchor='nw').place(x=665, y=15, width=105, height=25)

        self.filter_is_extended_id = [tk.BooleanVar() for _ in range(4)]
        position_y = 45
        for i in range(4):
            set_can_id_length = partial(self._set_filter_can_id_length, i)
            ttk.Checkbutton(config_section, variable=self.filter_is_extended_id[i], onvalue=True, offvalue=False,
                            bootstyle="info", command=set_can_id_length).place(x=700, y=position_y)
            position_y += 35
        ttk.Button(config_section, text='Configure',
                   command=self._config_bt).place(x=800, y=120, width=100, height=30)

    def _tab2_content(self, tab_name):
        # Create Treeview Frame
        tree_frame = ttk.Frame(tab_name)
        tree_frame.pack(padx=20, pady=15, side=tk.TOP, anchor=tk.NW)

        # Treeview Scrollbar
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Create Treeview
        self.my_tree = ttk.Treeview(tree_frame, yscrollcommand=tree_scroll.set, height=25)

        # Configure the scrollbar
        tree_scroll.config(command=self.my_tree.yview)

        # Define Our Columns
        self.my_tree['columns'] = ("Counter", "T_R", "Time", "Flags", "CAN_ID", "Len", "Data")

        # Formate Our Columns
        self.my_tree.column("#0", width=0, stretch=tk.NO)
        self.my_tree.column("Counter", anchor=tk.CENTER, width=65)
        self.my_tree.column("T_R", anchor=tk.CENTER, width=35)
        self.my_tree.column("Time", anchor=tk.CENTER, width=80)
        self.my_tree.column("Flags", anchor=tk.CENTER, width=50)
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

        self.my_tree.tag_configure('oddrow', background="#2E5090")
        self.my_tree.tag_configure('evenrow', background="#002147")
        # Pack to the screen
        self.my_tree.pack(expand=1)

        # TX msg section

        # Create an entry widget for CAN ID.
        ttk.Label(tab_name, text='CAN ID (hex):', font=self._FONT, anchor='nw').place(x=580, y=15, width=100, height=25)
        self.msg_can_id = tk.StringVar()
        self.msg_can_id.set('1FFFFFFF')
        val_hex_cb = self.root.register(self.val_hex_len)  # Register callback function to variable
        # Callback function will be called to validate the input whenever any keystroke changes the widget’s contents.
        self.entry_msg_can_id = ttk.Entry(tab_name, textvariable=self.msg_can_id,
                                          validate="key", validatecommand=(val_hex_cb, '%P', '%d', None, False))
        self.entry_msg_can_id.place(x=580, y=35, width=90)

        # Create an entry widget for DATA.
        ttk.Label(tab_name, text='DATA (hex):', font=self._FONT, anchor='nw').place(x=725, y=15, width=100, height=25)
        self.msg_can_data = tk.StringVar()
        self.msg_can_data.set('0001020304050607')
        # Callback function will be called to validate the input whenever any keystroke changes the widget’s contents.
        ttk.Entry(tab_name, textvariable=self.msg_can_data, validate="key",
                  validatecommand=(val_hex_cb, '%P', '%d', 16)).place(x=700, y=35, width=135)

        # Create a checkbutton widget for Extended Frame.
        self.msg_can_ext_frame = tk.StringVar()
        self.msg_can_ext_frame.set('1')
        ttk.Checkbutton(tab_name, text="Extended Frame", variable=self.msg_can_ext_frame, onvalue=1, offvalue=0,
                        bootstyle="info", command=self._set_tx_can_id_length, width=15).place(x=850, y=40)

        # Send Data button
        self.tx_controll = ttk.Button(tab_name, text='Send', command=self._tx_bt, state=NORMAL)
        self.tx_controll.place(x=855, y=76, width=130, height=30)

        # Device statistics display
        self.stats_var = tk.StringVar()
        self.stats_var.set("No device stats available.")
        stats_section = tk.Frame(tab_name)
        stats_section.place(x=585, y=180, width=420, height=150)
        if korlan.OS == 'Linux':
            self.stats_lst = [
                [tk.StringVar(value="RX frames:\n"), tk.StringVar(), tk.StringVar(value="TX frames:\n"), tk.StringVar()],
                [tk.StringVar(value="RX bytes:\n"), tk.StringVar(), tk.StringVar(value="TX bytes:\n"), tk.StringVar()],
                [tk.StringVar(value="Bus overruns:\n"), tk.StringVar(), None, None],
                [tk.StringVar(value="Bus state:\n"), tk.StringVar(), None, None]
            ]
        if korlan.OS == 'Windows':
            self.stats_lst = [
                [tk.StringVar(value="RX frames:\n"), tk.StringVar(), tk.StringVar(value="TX frames:\n"), tk.StringVar()],
                [tk.StringVar(value="RX bytes:\n"), tk.StringVar(), tk.StringVar(value="TX bytes:\n"), tk.StringVar()],
                [tk.StringVar(value="Bus overruns:\n"), tk.StringVar(), tk.StringVar(value="Bus warnings:\n"),tk.StringVar()],
                [tk.StringVar(value="Bus OFF's:\n"), tk.StringVar(), tk.StringVar(value="Canal status:\n"), tk.StringVar()]
            ]

        for i in range(len(self.stats_lst)):
            for j in range(len(self.stats_lst[0])):
                if j % 2 == 0:
                    label_width = 13
                else:
                    label_width = 11
                stats_table = ttk.Label(stats_section, textvariable=self.stats_lst[i][j],
                                        width=label_width, font=self._FONT, anchor='w')
                stats_table.grid(row=i, column=j)

        # Clear device statistics button
        ttk.Button(tab_name, text='Clear stats', command=self._clear_stats,
                   bootstyle='secondary').place(x=855, y=360, width=130, height=33)
        # Clear messages button
        ttk.Button(tab_name, text='Clear messages', bootstyle='secondary',
                   command=self._clear_msg).place(x=855, y=435, width=130, height=33)
        self.pause_resume_bt_text = tk.StringVar()
        self.pause_resume_bt_text.set('Pause RX')
        self.pause_resume_bt = ttk.Button(tab_name, textvariable=self.pause_resume_bt_text, bootstyle='secondary',
                                          command=self._stop_start_displaying_rx_messages)
        self.pause_resume_bt.place(x=700, y=435, width=130, height=33)

    def _stop_start_displaying_rx_messages(self):
        if '_can_rxtx_show' in self.root.bind('<<CAN_RX_event>>'):
            self.root.bind('<<CAN_RX_event>>', self._delete_rx_msgs_fom_queue)
            self.pause_resume_bt_text.set('Resume rx')
            self.pause_resume_bt.configure(bootstyle="warning")
        elif '_delete_rx_msgs_fom_queue' in self.root.bind('<<CAN_RX_event>>'):
            self.root.bind('<<CAN_RX_event>>', self._can_rxtx_show)
            self.pause_resume_bt_text.set('Pause RX')
            self.pause_resume_bt.configure(bootstyle="secondary")

    def _delete_rx_msgs_fom_queue(self, event):
        self.que.get()

    def _tab3_content(self, tab_name):
        for widgets in tab_name.winfo_children():
            widgets.destroy()
        if not self.obdii_tab.get():
            ttk.Label(tab_name, text='OBD2 option is not turned on.',
                      font=self._FONT).place(relx=.5, rely=.4, anchor="center")
        else:
            tab_name.grid_rowconfigure(0, weight=0)
            tab_name.grid_rowconfigure(1, weight=1)
            tab_name.grid_columnconfigure(0, weight=0)
            tab_name.grid_columnconfigure(1, weight=1)

            chck_parameters_section = tk.Frame(tab_name)
            chck_parameters_section.grid(row=0, column=0, rowspan=2, padx=(15, 25))

            data_section = tk.Frame(tab_name)
            data_section.grid(row=0, column=1)

            if_selected_obdii_sensors = [tk.BooleanVar() for _ in range(9)]
            tk.Label(chck_parameters_section, text='Select parameters to display (max 6):',
                     font=self._FONT).pack(pady=25)
            ttk.Checkbutton(chck_parameters_section, text="Engine Coolant temperature", bootstyle="info",
                            variable=if_selected_obdii_sensors[0], onvalue=True, offvalue=False, padding=3,
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[0])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Engine speed", variable=if_selected_obdii_sensors[1],
                            onvalue=True, offvalue=False, padding=3, bootstyle="info",
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[1])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Vehicle speed", variable=if_selected_obdii_sensors[2],
                            onvalue=True, offvalue=False, padding=3, bootstyle="info",
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[2])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Mass air flow rate", variable=if_selected_obdii_sensors[3],
                            onvalue=True, offvalue=False, padding=3, bootstyle="info",
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[3])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="O2 voltage", variable=if_selected_obdii_sensors[4],
                            onvalue=True, offvalue=False, padding=3, bootstyle="info",
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[4])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Throttle position", variable=if_selected_obdii_sensors[5],
                            onvalue=True, offvalue=False, padding=3, bootstyle="info",
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[5])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Evap. system vapor pressure", bootstyle="info",
                            variable=if_selected_obdii_sensors[6], onvalue=True, offvalue=False, padding=3,
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[6])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Engine oil temperature", bootstyle="info",
                            variable=if_selected_obdii_sensors[7], onvalue=True, offvalue=False, padding=3,
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[7])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Accelerator pedal position", bootstyle="info",
                            variable=if_selected_obdii_sensors[8], onvalue=True, offvalue=False, padding=3,
                            command=partial(self._checkmax_tab3, if_selected_obdii_sensors[8])).pack(anchor='w')

            ttk.Button(chck_parameters_section, text="Show data", width=15,
                       command=partial(self._create_sensors_list,
                                       if_selected_obdii_sensors, data_section)).pack(pady=35)

            tk.Label(chck_parameters_section,
                     text='WARNING:\nAvailable parameters depend on the\ncar brand.', font=('', 8)).pack(pady=(25, 0))

    def _create_sensors_list(self, if_selected_obdii_sensors, data_section):
        self.obdii_tab3_sensor_list.clear()
        if if_selected_obdii_sensors[0].get():
            self.obdii_tab3_sensor_list.append(["Temperature (°C)", self.temperature_value])
        if if_selected_obdii_sensors[1].get():
            self.obdii_tab3_sensor_list.append(["Engine speed (rpm)", self.engine_rpm_value])
        if if_selected_obdii_sensors[2].get():
            self.obdii_tab3_sensor_list.append(["Vehicle speed (km/h)", self.vehicle_speed_value])
        if if_selected_obdii_sensors[3].get():
            self.obdii_tab3_sensor_list.append(["Mass air flow rate (g/s)", self.maf_sensor_value])
        if if_selected_obdii_sensors[4].get():
            self.obdii_tab3_sensor_list.append(["O2 voltage", self.o2_voltage_value])
        if if_selected_obdii_sensors[5].get():
            self.obdii_tab3_sensor_list.append(["Throttle position (%)", self.throttle_position_value])
        if if_selected_obdii_sensors[6].get():
            self.obdii_tab3_sensor_list.append(["Evap syst vapor pressure (Pa)", self.evap_system_pressure_value])
        if if_selected_obdii_sensors[7].get():
            self.obdii_tab3_sensor_list.append(["Engine oil temperature (°C)", self.engine_oil_temp_value])
        if if_selected_obdii_sensors[8].get():
            self.obdii_tab3_sensor_list.append(["Accelerator pedal position (%)", self.accelerator_position_value])
        self._obdii_section(data_section)

    def _obdii_section(self, data_section):
        for widgets in data_section.winfo_children():
            widgets.destroy()
        x = 0
        y = 1
        pady = 25
        for item in self.obdii_tab3_sensor_list:
            section = ttk.LabelFrame(data_section, text=item[0], width=215, height=215)
            section.grid(row=x, column=y, padx=10, pady=pady)
            section.grid_rowconfigure(0, weight=1)
            section.grid_columnconfigure(0, weight=1)
            section.grid_propagate(0)
            ttk.Label(section, textvariable=item[1], font=self._FONT_BIG).grid()
            if y > 2:
                x = x + 1
                y = 1
                pady = (0, 25)
            else:
                y = y + 1

    def _checkmax_tab3(self, var):
        if var.get():
            if self.tab3_parameter_count < 6:
                self.tab3_parameter_count += 1
            else:
                var.set(False)
        else:
            self.tab3_parameter_count -= 1

    def _tab4_content(self, tab_name):
        for widgets in tab_name.winfo_children():
            widgets.destroy()
        if not self.obdii_tab.get():
            ttk.Label(tab_name, text='OBD2 option is not turned on.',
                      font=self._FONT).place(relx=.5, rely=.4, anchor="center")
        else:
            tab_name.grid_rowconfigure(0, weight=0)
            tab_name.grid_rowconfigure(1, weight=1)
            tab_name.grid_columnconfigure(0, weight=0)
            tab_name.grid_columnconfigure(1, weight=1)

            chck_parameters_section = tk.Frame(tab_name, pady=25)
            chck_parameters_section.grid(row=0, column=0, rowspan=2, padx=(15, 0))

            tab4_data_section = tk.Frame(tab_name)
            tab4_data_section.grid(row=0, column=1)

            if_checked_obdii_diagrams_list = [tk.BooleanVar() for _ in range(9)]

            tk.Label(chck_parameters_section, text='Select diagrams to display:\n(max 4)').pack(pady=(0, 15))

            ttk.Checkbutton(chck_parameters_section, text="Engine Coolant\ntemperature", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[0], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[0])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Engine speed", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[1], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[1])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="Vehicle speed", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[2], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[2])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="Mass air flow rate", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[3], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[3])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="O2 voltage", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[4], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[4])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="Throttle position", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[5], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[5])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="Evap. system\nvapor pressure", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[6], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[6])).pack(anchor='w')

            ttk.Checkbutton(chck_parameters_section, text="Engine oil temperature", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[7], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[7])).pack(anchor='w', pady=5)

            ttk.Checkbutton(chck_parameters_section, text="Accelerator pedal position", bootstyle="info",
                            variable=if_checked_obdii_diagrams_list[8], onvalue=True, offvalue=False,
                            command=partial(self._checkmax_tab4,
                                            if_checked_obdii_diagrams_list[8])).pack(anchor='w', pady=5)

            ttk.Button(chck_parameters_section, text="Show diagrams",
                       command=partial(self._create_diagrams_data_list,
                                       tab4_data_section, if_checked_obdii_diagrams_list)).pack(pady=(30, 40))

            tk.Label(chck_parameters_section,
                     text='WARNING:\nAvailable parameters depend on the\ncar brand.', font=('', 8)).pack()

    def _draw_diagrams(self, tab_name):
        for widgets in tab_name.winfo_children():
            widgets.destroy()
        x = 0
        y = 1
        for item in self.obdii_diagrams_data_list:
            fig = Figure(figsize=(3.7, 2.3), facecolor="#003366")
            plot = fig.add_subplot(111, facecolor="#DFECEC")
            canvas = FigureCanvasTkAgg(fig, master=tab_name)
            canvas_widget = canvas.get_tk_widget()
            canvas_widget.configure(highlightthickness=1, highlightbackground="#5e82a7", highlightcolor="#5e82a7")
            canvas_widget.grid(row=x, column=y, padx=(5, 0), pady=(10, 0))
            ani = FuncAnimation(fig, partial(self._plot, plot=plot, data_deque=item[1],
                                             title=item[0]), interval=1022.5)
            canvas.draw()
            if y > 1:
                x = x + 1
                y = 1
            else:
                y = y + 1

    def _plot(self, i, plot, data_deque, title):
        plot.cla()
        plot.plot(data_deque)
        plot.tick_params(
            axis='x',
            which='both',
            bottom=False,
            top=False,
            labelbottom=False)
        plot.tick_params(
            axis='y',
            colors='white'
        )
        plot.margins(x=0.25, y=0.1)
        plot.scatter(len(data_deque) - 1, data_deque[-1])
        plot.text(len(data_deque) - 1, data_deque[-1] + 2, "{}".format(data_deque[-1]))
        # plot.set_ylim(y_lim_bottom, y_lim_top)
        plot.set_title(title, fontsize=15, color="white")

    def _create_diagrams_data_list(self, tab4_data_section, if_checked_obdii_diagrams_list):
        self.obdii_diagrams_data_list.clear()
        if if_checked_obdii_diagrams_list[0].get():
            self.obdii_diagrams_data_list.append(["Temperature (°C)", self.engine_temperature_deque])
        if if_checked_obdii_diagrams_list[1].get():
            self.obdii_diagrams_data_list.append(["Engine speed (rpm)", self.engine_rpm_deque])
        if if_checked_obdii_diagrams_list[2].get():
            self.obdii_diagrams_data_list.append(["Vehicle speed (km/h)", self.vehicle_speed_deque])
        if if_checked_obdii_diagrams_list[3].get():
            self.obdii_diagrams_data_list.append(["Mass air flow rate (g/s)", self.maf_sensor_deque])
        if if_checked_obdii_diagrams_list[4].get():
            self.obdii_diagrams_data_list.append(["O2 voltage", self.o2_voltage_deque])
        if if_checked_obdii_diagrams_list[5].get():
            self.obdii_diagrams_data_list.append(["Throttle position (%)", self.throttle_position_deque])
        if if_checked_obdii_diagrams_list[6].get():
            self.obdii_diagrams_data_list.append(["Evap. system vapor pressure (Pa)", self.evap_system_pressure_deque])
        if if_checked_obdii_diagrams_list[7].get():
            self.obdii_diagrams_data_list.append(["Engine oil temperature (°C)", self.engine_oil_temp_deque])
        if if_checked_obdii_diagrams_list[8].get():
            self.obdii_diagrams_data_list.append(["Accelerator pedal position (%)", self.accelerator_position_deque])
        self._draw_diagrams(tab4_data_section)

    def _checkmax_tab4(self, var):
        if var.get():
            if self.tab4_parameter_count < 4:
                self.tab4_parameter_count += 1
            else:
                var.set(False)
        else:
            self.tab4_parameter_count -= 1

    if korlan.OS == 'Windows':
        # Under windows CANAL_API is used to get status and statistics.
        # CANAL_API specifications can be found here:
        # https://www.8devices.com/media/products/usb2can_korlan/downloads/CANAL_API.pdf
        def _update_stats(self):
            status = CanalStatus()
            self.bus.can.get_status(self.bus.handle, byref(status))
            # print(status.channel_status, status.lasterrorcode, status.lasterrorsubcode, status.lasterrorstr)
            canal_status_passive = 0x40000000
            canal_status_bus_off = 0x80000000
            canal_status_bus_warn = 0x20000000

            self.bus_offline = self.bus_passive = self.bus_warning = False
            self.canal_status = 'Ok'
            if status.channel_status & canal_status_bus_off:
                self.bus_offline = True
                self.canal_status = "Bus offline"
            elif status.channel_status & canal_status_passive:
                self.bus_passive = True
                self.canal_status = "Bus passive"
            elif status.channel_status & canal_status_bus_warn:
                self.bus_warning = True
                self.canal_status = "Bus warning"
            self.rx_err = (status.channel_status >> 8) & 0xff
            self.tx_err = status.channel_status & 0xff

            statistics = CanalStatistics()
            self.bus.can.get_statistics(self.bus.handle, byref(statistics))
            self.rx_frames += statistics.ReceiveFrams
            self.tx_frames += statistics.TransmistFrams
            self.rx_bytes += statistics.ReceiveData
            self.tx_bytes += statistics.TransmitData
            self.bus_overr += statistics.Overruns
            self.bus_warnings += statistics.BusWarnings
            self.bus_off += statistics.BusOff

            self.stats_lst[0][1].set(f'{self.rx_frames}\n')
            self.stats_lst[0][3].set(f'{self.rx_bytes}\n')
            self.stats_lst[1][1].set(f'{self.rx_bytes}\n')
            self.stats_lst[1][3].set(f'{self. tx_bytes}\n')
            self.stats_lst[2][1].set(f'{self.bus_overr}\n')
            self.stats_lst[2][2].set(f'{self.bus_warning}\n')
            self.stats_lst[3][1].set(f'{self.bus_off}\n')
            self.stats_lst[3][2].set(f'{self.canal_status}\n')

            self.statusbar_connection.config(text=f'Korlan ID {self.can_id}: is connected to CAN bus at bit rate '
                                                  f'{korlan.bit_rates_menu[self.can_datarate]}')
            self.statusbar_txrx.config(text=f'RX err: {self.rx_err}   TX err: {self.tx_err}')
            self.root.after(1000, self._update_stats)

    elif korlan.OS == 'Linux':
        def _update_stats(self):
            status = can.bus.BusState
            self.bus_state = ''
            if self.bus.state == status.ACTIVE:
                self.bus_state = 'Active'
            elif self.bus.state == status.ERROR:
                self.bus_state = 'Error'
            elif self.bus.state == status.PASSIVE:
                self.bus_state = 'Passive'

            self.rx_frames, \
                self.rx_bytes, \
                self.tx_frames, \
                self.tx_bytes, \
                self.bus_overr, \
                self.rx_err, \
                self.tx_err = korlan.get_statistics(self.can_id,
                                                    self.rx_frames_count_starting_point,
                                                    self.rx_bytes_count_starting_point,
                                                    self.tx_frames_count_starting_point,
                                                    self.tx_bytes_count_starting_point,
                                                    self.bus_overr_count_starting_point)

            self.stats_lst[0][1].set(f'{self.rx_frames}\n')
            self.stats_lst[0][3].set(f'{self.tx_frames}\n')
            self.stats_lst[1][1].set(f'{self.rx_bytes}\n')
            self.stats_lst[1][3].set(f'{self. tx_bytes}\n')
            self.stats_lst[2][1].set(f'{self.bus_overr}\n')
            self.stats_lst[3][1].set(f'{self.bus_state}\n')

            self.statusbar_connection.config(
                text=f'Korlan ID {list(self.korlan_ids.keys())[list(self.korlan_ids.values()).index(self.can_id)]}: '
                     f'is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.')
            self.statusbar_txrx.config(text=f'RX err: {self.rx_err}   TX err: {self.tx_err}')
            self.root.after(1000, self._update_stats)

    def _clear_stats(self):
        if korlan.OS == 'Linux':
            self.rx_frames_count_starting_point, \
                self.rx_bytes_count_starting_point, \
                self.tx_frames_count_starting_point, \
                self.tx_bytes_count_starting_point, \
                self.bus_overr_count_starting_point, \
                self.rx_err, \
                self.tx_err = korlan.get_raw_statistics(self.can_id)

        if korlan.OS == 'Windows':
            self.rx_frames = 0
            self.tx_frames = 0
            self.rx_bytes = 0
            self.tx_bytes = 0
            self.bus_overr = 0
            self.bus_warnings = 0
            self.bus_off = 0

    def _clear_msg(self):
        self.my_tree.delete(*self.my_tree.get_children())
        self.msg_count = 0

    def _set_filter_can_id_length(self, i):
        if self.filter_is_extended_id[i].get() is True:
            self.filter_can_id_length[i] = 8
        else:
            self.filter_can_id_length[i] = 3
            # Remove the excess characters so that the can id would not be extended
            text = self.entry_filter_msg_can_ids[i].get()
            text = text[:3]
            self.entry_filter_msg_can_ids[i].delete(0, 'end')
            self.entry_filter_msg_can_ids[i].insert(0, text)

    def _set_tx_can_id_length(self):
        if self.msg_can_ext_frame.get() == '1':
            self.tx_can_id_length = 8
        else:
            self.tx_can_id_length = 3
            # Remove the excess characters so that the can id would not be extended
            text = self.entry_msg_can_id.get()
            text = text[:3]
            self.entry_msg_can_id.delete(0, 'end')
            self.entry_msg_can_id.insert(0, text)

    def is_hex(self, s):
        hex_digits = set(string.hexdigits)
        # If s is long, then it is faster to check against a set
        return all(c in hex_digits for c in s)

    def val_hex_len(self, inStr, acttyp, max_length=None, filtering=None, i=None):
        if inStr == '':
            inStr = '0'
        if max_length != 'None':
            length = int(max_length)
        else:
            if filtering == '1':
                length = int(self.filter_can_id_length[int(i)])
            else:
                length = int(self.tx_can_id_length)
        if len(inStr) > length:
            return False
        if acttyp == '1':  # New character inserted
            if not self.is_hex(inStr):
                return False
        return True

    def _status_bar(self):
        statusbar_section = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        statusbar_section.pack(side=tk.BOTTOM, fill='both')
        self.statusbar_connection = tk.Label(statusbar_section, text="Not connected to Korlan device.",
                                             anchor='w', padx=10)
        self.statusbar_connection.pack(side='left')

        self.statusbar_txrx = tk.Label(statusbar_section, text='', anchor='e', padx=10)
        self.statusbar_txrx.pack(side='right')

    if korlan.OS == 'Windows':
        def _id_changed(self, *args):
            self.can_id_tmp = self.korlan_id_text.get()

    elif korlan.OS == 'Linux':
        def _id_changed(self, *args):
            self.can_id_tmp = self.korlan_ids[self.korlan_id_text.get()]

    def _rate_changed(self, *args):
        self.can_datarate_tmp = korlan.bit_rates_menu.index(self.bit_rate_text.get())

    def _chk(self):
        if self.silent.get() or self.loopback.get():
            self.obdii_tab.set(False)  # need to set the value of var1 to update chk1
            self.obdii_checkbox.configure(state=DISABLED)
        else:
            self.obdii_checkbox.configure(state=NORMAL)

    def _config_bt(self):
        device_details_text = ''
        self.can_datarate = self.can_datarate_tmp
        self.can_id = self.can_id_tmp
        self.filters = []
        for i in range(4):  # Preparing filters' dictionary
            if self.filter_can_masks[i].get() == "" or self.filter_msg_can_ids[i].get() == "":
                continue
            self.filters.append({
                "can_id": int(self.filter_msg_can_ids[i].get(), 16),
                "can_mask": int(self.filter_can_masks[i].get(), 16),
                "extended": self.filter_is_extended_id[i].get()
            })

        self.stop_obdii_tx_thread = True
        self.stop_rx_thread = True  # Shutting down RX thread, so it would be restarted with new bus interface.
        time.sleep(0.5)

        # Create new can bus interface
        if korlan.OS == 'Windows':
            check_flags = self.loopback.get() | self.silent.get() | self.dis_auto_retr.get()
            # print('flags = ', bin(check_flags))
            self.bus, vendor_iter = korlan.get_bus(self.bus, id=self.can_id,
                                                   rate=korlan.bit_rates[self.can_datarate] * 1000,
                                                   bus_flags=check_flags, filters=self.filters)
            if check_flags == 1 or check_flags == 5:
                self.tx_controll.config(state=DISABLED)
            else:
                self.tx_controll.config(state=NORMAL)

        elif korlan.OS == 'Linux':
            self.bus, vendor_iter = korlan.get_bus(self.bus, id=self.can_id,
                                                   new_rate=korlan.bit_rates[self.can_datarate] * 1000,
                                                   is_listen_only=self.silent.get(), is_loopback=self.loopback.get(),
                                                   is_one_shot=self.dis_auto_retr.get(), filters=self.filters)
            if self.silent.get() and not self.loopback.get():
                self.tx_controll.config(state=DISABLED)
            else:
                self.tx_controll.config(state=NORMAL)
        # Show device details
        for e, v in vendor_iter:
            device_details_text += f'{e}:\t\t{v}\n'
        self.details_var.set(device_details_text)

        if korlan.OS == 'Windows':
            self.statusbar_connection.config(
                text=f'Korlan ID {self.can_id}: is connected to CAN bus at bit rate '
                     f'{korlan.bit_rates_menu[self.can_datarate]}.')
        elif korlan.OS == 'Linux':
            self.statusbar_connection.config(
                text=f'Korlan ID {list(self.korlan_ids.keys())[list(self.korlan_ids.values()).index(self.can_id)]}: '
                     f'is connected to CAN bus at bit rate {korlan.bit_rates_menu[self.can_datarate]}.')

        if not self.can_rx_thread:
            self.stop_rx_thread = False
            self.can_rx_thread = threading.Thread(target=korlan.rx_msgs,
                                                  args=(self.bus, self.root,
                                                        lambda: self.stop_rx_thread,
                                                        self.que, self.obdii_tab.get()),
                                                  daemon=True)
            self.root.bind('<<CAN_RX_event>>', self._can_rxtx_show)
            self.can_rx_thread.start()
        else:
            self.can_rx_thread.join(2)  # Stop can_rx_thread
            if not self.can_rx_thread.is_alive():
                self.stop_rx_thread = False
                # Start new can_rx_thread with new can bus interface
                self.can_rx_thread = threading.Thread(target=korlan.rx_msgs,
                                                      args=(self.bus, self.root,
                                                            lambda: self.stop_rx_thread,
                                                            self.que, self.obdii_tab.get()),
                                                      daemon=True)
                self.can_rx_thread.start()

        if self.can_obdii_tx_thread is not None:
            self.can_obdii_tx_thread.join()
        if self.obdii_tab.get():
            self.engine_rpm_deque = collections.deque(np.zeros(15))
            self.engine_temperature_deque = collections.deque(np.zeros(15))
            self.throttle_position_deque = collections.deque(np.zeros(15))
            self.vehicle_speed_deque = collections.deque(np.zeros(15))
            self.maf_sensor_deque = collections.deque(np.zeros(15))
            self.o2_voltage_deque = collections.deque(np.zeros(15))
            self.evap_system_pressure_deque = collections.deque(np.zeros(15))
            self.engine_oil_temp_deque = collections.deque(np.zeros(15))
            self.accelerator_position_deque = collections.deque(np.zeros(15))

            self.stop_obdii_tx_thread = False
            self.can_obdii_tx_thread = threading.Thread(target=self._tx_obdii, daemon=True)
            self.can_obdii_tx_thread.start()

        self._clear_stats()
        self.tab3_parameter_count = 0
        self.tab4_parameter_count = 0
        self.rx_err = 0
        self.tx_err = 0
        self._update_stats()
        self._tab3_content(self.tab3)
        self._tab4_content(self.tab4)

    def _can_rxtx_show(self, event):
        msgl = self.que.get()
        self.msg_count += 1
        dta = " ".join("{:02X}".format(c) for c in msgl[5])
        if korlan.OS == "Windows":
            message_time = msgl[1] / 1000
        elif korlan.OS == "Linux":
            if msgl[0] == 'r':
                message_time = msgl[1] - self.start_timestamp
            else:
                message_time = msgl[1]
        self.my_tree.insert(parent='', index='end', iid=self.msg_count, text="",
                            values=(self.msg_count,  # msg count during session
                                    msgl[0],  # tx/rx
                                    f'{message_time:.3f}',  # time stamp
                                    msgl[2],  # flags
                                    f'{msgl[3]:08X}',  # CAN ID
                                    msgl[4],  # dlc
                                    dta
                                    ),
                            tags=('evenrow' if self.msg_count % 2 else 'oddrow',)
                            )
        self.my_tree.yview_moveto(1)  # show last received msg's

        # When messages count reaches 10000, delete 1000 first rows to save memory
        rows_len = len(self.my_tree.get_children())
        if rows_len > 9999:
            del_msg_count = int(rows_len / 10)
            for row in self.my_tree.get_children():
                self.my_tree.delete(row)
                del_msg_count -= 1
                if del_msg_count == 0:
                    break

        if self.obdii_tab.get() is True and msgl[0] == 'r' and msgl[3] == PID_REPLY:
            self._update_obdii(msgl)  # Show obdii data

    def _tx_bt(self):
        id_s = self.msg_can_id.get()
        data = []
        input_data = self.msg_can_data.get()
        ext = self.msg_can_ext_frame.get()
        if ext == '1':
            is_extended_id = True
        else:
            is_extended_id = False
        for i in range(0, len(input_data), 2):
            data.append(int(input_data[i + 0:i + 2], 16))
        korlan.tx_msg(self.bus, self.que, int(id_s, 16), data, is_extended_id)
        if not self.que.empty():
            self._can_rxtx_show(None)

    def _tx_obdii(self):
        while True:
            if self.stop_obdii_tx_thread:
                break
            # Send an Engine coolant temperature request
            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, ENGINE_COOLANT_TEMP, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            if self.stop_obdii_tx_thread:
                break
            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, ENGINE_RPM, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            if self.stop_obdii_tx_thread:
                break
            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, VEHICLE_SPEED, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            if self.stop_obdii_tx_thread:
                break
            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, MAF_SENSOR, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            if self.stop_obdii_tx_thread:
                break
            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, O2_VOLTAGE, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            if self.stop_obdii_tx_thread:
                break
            korlan.tx_msg(self.bus, self.que, PID_REQUEST, [0x02, 0x01, THROTTLE, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, EVAP_SYSTEM_VAPOR_PRESSURE, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, ENGINE_OIL_TEMP, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            korlan.tx_msg(self.bus, self.que, PID_REQUEST,
                          [0x02, 0x01, ACCELERATOR_PEDAL_POSITION, 0x00, 0x00, 0x00, 0x00, 0x00], False)
            if not self.que.empty():
                self._can_rxtx_show(None)
            time.sleep(0.0025)

            time.sleep(1)
        pass

    def _update_obdii(self, msgl):
        if msgl[5][2] == ENGINE_COOLANT_TEMP:
            engine_temperature = msgl[5][3] - 40  # Convert data into temperature in degree C
            self.temperature_value.set('{0:d}'.format(engine_temperature))
            self.engine_temperature_deque.popleft()
            self.engine_temperature_deque.append(engine_temperature)
        if msgl[5][2] == ENGINE_RPM:
            rpm = round(((msgl[5][3] * 256) + msgl[5][4]) / 4)  # Convert data to rpm
            self.engine_rpm_value.set('{0:d}'.format(rpm))
            self.engine_rpm_deque.popleft()
            self.engine_rpm_deque.append(rpm)
        if msgl[5][2] == VEHICLE_SPEED:
            vehicle_speed = msgl[5][3]
            self.vehicle_speed_value.set('{0:d}'.format(vehicle_speed))
            self.vehicle_speed_deque.popleft()
            self.vehicle_speed_deque.append(vehicle_speed)
        if msgl[5][2] == MAF_SENSOR:
            maf_sensor = round((256 * msgl[5][3] + msgl[5][4]) / 100)
            self.maf_sensor_value.set('{0:d}'.format(maf_sensor))
            self.maf_sensor_deque.popleft()
            self.maf_sensor_deque.append(maf_sensor)
        if msgl[5][2] == O2_VOLTAGE and msgl[5][4] != 0xFF:
            o2_voltage = msgl[5][3] / 200
            self.o2_voltage_value.set('{0:.3f}'.format(o2_voltage))
            self.o2_voltage_deque.popleft()
            self.o2_voltage_deque.append(o2_voltage)
        if msgl[5][2] == THROTTLE:
            throttle = round((msgl[5][3] * 100) / 255)
            self.throttle_position_value.set('{0:d}'.format(throttle))
            self.throttle_position_deque.popleft()
            self.throttle_position_deque.append(throttle)
        if msgl[5][2] == EVAP_SYSTEM_VAPOR_PRESSURE:
            evap_pressure = round(((256 * msgl[5][3] + msgl[5][4]) / 4))
            self.evap_system_pressure_value.set('{0:d}'.format(evap_pressure))
            self.evap_system_pressure_deque.popleft()
            self.evap_system_pressure_deque.append(evap_pressure)
        if msgl[5][2] == ENGINE_OIL_TEMP:
            engine_oil_temperature = msgl[5][3] - 40
            self.engine_oil_temp_value.set('{0:d}'.format(engine_oil_temperature))
            self.engine_oil_temp_deque.popleft()
            self.engine_oil_temp_deque.append(engine_oil_temperature)
        if msgl[5][2] == ACCELERATOR_PEDAL_POSITION:
            accelerator = round((msgl[5][3] * 100) / 255)
            self.accelerator_position_value.set('{0:d}'.format(accelerator))
            self.accelerator_position_deque.popleft()
            self.accelerator_position_deque.append(accelerator)


if korlan.OS == 'Windows' or 'Linux':
    MainGUI().root.mainloop()
else:
    messagebox.showerror("Error", "The program is not supported on this operating system.")
