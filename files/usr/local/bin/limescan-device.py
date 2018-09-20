#!/usr/bin/python3

import sys
import requests
import json
import subprocess
import csv
import os
from datetime import datetime
import configparser
from random import randint


def LimeScan (url, configurl, devicename, deviceconfig):
    if deviceconfig['custom_config'] is None:
        params = "-f 600M:1000M -C 0 -A LNAW -w 35M -r 16M -OSR 8 -b 512 -g 48 -n 64 -T 1"
    else:
        params = deviceconfig['custom_config']
    subprocess.Popen(["LimeScan " + params + " -O 'scan-output'"], shell=True).wait()

    first_timestamp = None
    last_timestamp = None
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
            freqLow = str(int(float(items[2]) * 1e6))
            freqHigh = str(int(float(items[3]) * 1e6))
            freqStep = str(int(float(items[4])))
            dB = '"' + ",".join([str(item).strip() for item in items[6:]]) + '"'
            influxline = "power,sensor=" + devicename + " hzlow=" + freqLow + ",hzhigh=" + freqHigh + ",step=" + freqStep + ",samples=3,dbs=" + dB + " " + nanoseconds
            lines += '\n' + influxline
            last_timestamp = nanoseconds
            i += 1
        sqlite_response = requests.post(configurl + "scans", json = {"device_config_id": deviceconfig['device_config_id'], "scan_start_time": first_timestamp, "scan_finish_time": last_timestamp })
        influxlines = ""
        scanid = json.loads(sqlite_response.text)['stmt']['lastID']
        for line in lines.split('\n'):
            columns = line.split(' ')
            if (len(columns) > 1):
                columns[-2] = str(columns[-2]) + ',scanid=' + str(scanid)
                influxlines += ' '.join(columns) + '\n'
        influx_response = requests.post(url, data=influxlines)
        #print(influxlines)


def GSM (url, configurl, devicename, deviceconfig):
    band = "GSM900"
    if deviceconfig['scan_band'] is not None:
        band = deviceconfig['scan_band']
    params = "--args rtl -b" + band

    output = subprocess.Popen(["grgsm_scanner " + params], shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    out, err = output.communicate()
    output.wait()
    print("command:", "grgsm_scanner " + params)
    print("out:", out)
    print("error:", err)


    # dummy = b'linux; GNU C++ version 6.2.0 20161010; Boost_106100; UHD_003.009.005-0-unknown\nARFCN:   86, Freq:  952.2M, CID:     0, LAC:     0, MCC:   0, MNC:   0, Pwr: -44\nARFCN:   96, Freq:  954.2M, CID:     0, LAC:     0, MCC:   0, MNC:   0, Pwr: -45\nARFCN:  105, Freq:  956.0M, CID: 32857, LAC: 21469, MCC: 234, MNC:  10, Pwr: -' + bytes(str(randint(20,60)), encoding='utf-8') + b'\nARFCN:  105, Freq:  956.0M, CID: 32857, LAC: 21469, MCC: 234, MNC:  30, Pwr: -' + bytes(str(randint(20,60)), encoding='utf-8')
    #dummy = b'linux; GNU C++ version 6.2.0 20161010; Boost_106100; UHD_003.009.005-0-unknown\n\n'
    dummy = out
    dummysplit = str(dummy, 'utf-8').split('\n')
    lines = ""
    items = []
    first_timestamp = datetime.now().timestamp() * 1e9
    for item in dummysplit[1:]:
        subitems = {}
        print(item)
        commasplit = item.split(',')
        commasplit = [i.split(':') for i in commasplit]
        #print("commasplit: " + commasplit)
        for i in commasplit:
            if i != "" and i[0] and i[1]:
                subitems[i[0].strip()] = i[1].strip()
        try:
            if subitems['ARFCN'] and int(subitems['ARFCN']) > 0 and int(subitems['MCC']) > 0 and int(subitems['MNC']) > 0 and (int(subitems['Pwr']) > 0 or int(subitems['Pwr']) < 0):
                items.append(subitems)
                current_timestamp = str(round(datetime.now().timestamp() * 1e9))
                influxline = 'gsm,sensor=' + devicename + ',ARFCN=' + subitems['ARFCN'] + ',CID=' + subitems['CID'] + ',LAC=' + subitems['LAC'] + ',MCC=' + subitems['MCC'] + ',MNC=' + subitems['MNC'] + ',band=' + band + ' Pwr=' + subitems['Pwr'] + " " + current_timestamp
                lines += '\n' + influxline
        except:
            continue
    last_timestamp = datetime.now().timestamp() * 1e9
    if len(lines) > 0:
        sqlite_response = requests.post(configurl + "scans", json = {"device_config_id": deviceconfig['device_config_id'], "scan_start_time": first_timestamp, "scan_finish_time": last_timestamp })
        influxlines = ""
        scanid = json.loads(sqlite_response.text)['stmt']['lastID']
        for line in lines.split('\n'):
            columns = line.split(' ')
            if (len(columns) > 1):
                columns[-2] = str(columns[-2]) + ',scanid=' + str(scanid)
                influxlines += ' '.join(columns) + '\n'
        influx_response = requests.post(url, data=influxlines)
        print(influxlines, influx_response.text)

config = configparser.ConfigParser()
configfile = config.read(['config.ini', '/pantavisor/user-meta/limescan-config.ini'])
if len(configfile) == 0:
    raise ValueError("Configuration file missing, rename config.example.ini to config.ini")

url = config["DEFAULT"]["DATA_URL"] + "write?db=limescan"
configurl = config["DEFAULT"]["API_URL"]
devicename = config["DEFAULT"]["DEVICE_NAME"]

deviceconfig = json.loads(requests.get(configurl + "devices/" + devicename).text)

if deviceconfig['scan_type'] == "power":
    LimeScan(url, configurl, devicename, deviceconfig)

if deviceconfig['scan_type'] == "gsm":
    GSM(url, configurl, devicename, deviceconfig)

