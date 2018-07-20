import sys
import requests
import json
import subprocess
import csv
from datetime import datetime
import configparser

config = configparser.ConfigParser()
configfile = config.read('config.ini')
if len(configfile) == 0:
    raise ValueError("Configuration file missing, rename config.example.ini to config.ini")

url = config["DEFAULT"]["DATA_URL"] + "write?db=limemicro"
configurl = config["DEFAULT"]["API_URL"]
devicename = config["DEFAULT"]["DEVICE_NAME"]

deviceconfig = json.loads(requests.get(configurl + "devices/" + devicename).text)[0]
command = "LimeScan"
first_timestamp = None
last_timestamp = None

if deviceconfig['scan_type'] == "limescan":
    command = "LimeScan"
else:
    command = "LimeMon"


filename = devicename
subprocess.Popen([command + " -f 600M:1000M -C 0 -A LNAW -w 35M -r 16M -OSR 8 -b 512 -g 48 -n 64 -O 'scan-output' -T 1"], shell=True).wait()

with open('scan-output/scan-outputPk.csv', newline='') as csvfile:

    reader = csv.reader(csvfile, delimiter=',')
    reader.__next__() #first row is filename, skip it
    i = 1
    lines = ""
    for items in reader:
        timestamp_obj = datetime.strptime(items[0].strip() + " " + items[1].strip(), '%Y-%m-%d %H:%M:%S')
        nanoseconds = str(round(timestamp_obj.timestamp() * 1e9) + i)
        if first_timestamp is None:
            first_timestamp = nanoseconds
        freqLow = str(items[2].strip())
        freqHigh = str(items[3].strip())
        freqStep = str(items[4].strip())
        dB = '"' + ",".join([str(item).strip() for item in items[6:]]) + '"'

        influxline = "spectrum,sensor=" + devicename + " hzlow=" + freqLow + ",hzhigh=" + freqHigh + ",step=" + freqStep + ",samples=3,dbs=" + dB + " " + nanoseconds
        lines += '\n' + influxline
        last_timestamp = nanoseconds
        i += 1
    influx_response = requests.post(url, data=lines)
    sqlite_response = requests.post(configurl + "scans", json = {"device_config_id": deviceconfig['device_config_id'], "scan_start_time": first_timestamp, "scan_finish_time": last_timestamp })
