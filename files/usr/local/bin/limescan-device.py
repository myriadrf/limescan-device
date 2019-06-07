#!/usr/bin/python3

import sys
import requests
import json
import subprocess
import csv
import os
import hashlib
from datetime import datetime
import configparser
from random import randint
import collections
import time

def getDigest(input):
    print(input)
    block_size = 65536
    sha256 = hashlib.sha256()
    sha256.update(input.encode('utf-8'))
    digest = sha256.hexdigest()
    return(digest)

def lineAddScanID(line, scanid):
    columns = line.split(' ')
    newline = ""
    if (len(columns) > 1):
        columns[-2] = str(columns[-2]) + ',scanid="' + str(scanid) + '"'
        newline += ' '.join(columns)
    return newline

def LimeScan (configurl, devicename, configid, custom_config):
    if custom_config is None:
        params = "-f 600M:1000M -C 0 -A LNAW -w 35M -r 16M -OSR 8 -b 512 -g 48 -n 64 -T 1"
    else:
        params = custom_config
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

        scan_digest = getDigest(lines)
        metadata = {
            "device_config_id": configid,
            "scan_start_time": float(first_timestamp),
            "scan_finish_time": float(last_timestamp),
            "scan_digest": scan_digest
        }

        scanid = getDigest(json.dumps(metadata, sort_keys=True))
        metadata["id"] = scanid


        influxlines = ""
        for line in lines.split('\n'):
            influxlines += lineAddScanID(line, scanid) + '\n'

        data = {
            "metadata": metadata,
            "scans": influxlines
        }

        sqlite_response = requests.post(configurl + "scans", json = data)


def GSM (configurl, devicename, configid, scan_band):
    band = "GSM900"
    if scan_band is not None:
        band = scan_band
    params = "-s0.8e6 -g56 -f 20000000 -O /tmp/scan-outputGSM -b " + band
    first_timestamp = datetime.now().timestamp() * 1e9
    subprocess.Popen(["grgsm_scanner " + params], shell=True).wait()
    print("command:", "grgsm_scanner " + params)

    last_timestamp = datetime.now().timestamp() * 1e9
    lines = ""
    items = []

    with open('/tmp/scan-outputGSM') as resultsfile:
        dummysplit = resultsfile.readlines()
        for item in dummysplit:
            subitems = {}
            print(item)
            commasplit = item.split(',')
            commasplit = [i.split(':') for i in commasplit]
            for i in commasplit:
                if i != "" and i[0] and i[1]:
                    subitems[i[0].strip()] = i[1].strip()
            try:
                if subitems['ARFCN'] and int(subitems['ARFCN']) > 0 and int(subitems['MCC']) > 0 and int(subitems['LAC']) > 0 and int(subitems['CID']) > 0 and int(subitems['MNC']) > 0 and (int(subitems['Pwr']) > 0 or int(subitems['Pwr']) < 0):
                    items.append(subitems)
                    current_timestamp = str(round(datetime.now().timestamp() * 1e9))
                    influxline = 'gsm,sensor=' + devicename + ',ARFCN=' + subitems['ARFCN'] + ',CID=' + subitems['CID'] + ',LAC=' + subitems['LAC'] + ',MCC=' + subitems['MCC'] + ',MNC=' + subitems['MNC'] + ',band=' + band + ' Pwr=' + subitems['Pwr'] + " " + current_timestamp
                    lines += '\n' + influxline
            except:
                continue

    for line in lines.split('\n'):
        line = line.strip()
        print(line)
        scan_digest = getDigest(line)
        metadata = {
            "device_config_id": configid,
            "scan_start_time": first_timestamp,
            "scan_finish_time": last_timestamp,
            "scan_digest": scan_digest
        }
        scanid = getDigest(json.dumps(metadata, sort_keys=True))
        metadata["id"] = scanid
        line = lineAddScanID(line, scanid)
        print(line)

        data = {
            "metadata": metadata,
            "scans": line
        }
        sqlite_response = requests.post(configurl + "scans", json = metadata)

config = configparser.ConfigParser()
configfile = config.read(['config.ini', '/pantavisor/user-meta/limescan-config.ini'])
if len(configfile) == 0:
    raise ValueError("Configuration file missing, rename config.example.ini to config.ini")

configurl = config["DEFAULT"]["API_URL"]
devicename = config["DEFAULT"]["DEVICE_NAME"]

def checkSchedule():
    interval_seconds = 0
    scan_schedule_start = 0
    deviceconfig = json.loads(requests.get(configurl + "devices/" + devicename).text)
    configid = deviceconfig['device_config_id']
    interval_seconds = deviceconfig['scan_interval']
    scan_schedule_start = time.time()

    print(deviceconfig)

    if deviceconfig['scan_type_1'] == 'null':
        # Single Scan
        print("single scan")
        if deviceconfig['scan_type'] == "power":
            LimeScan(configurl, devicename, configid, deviceconfig['custom_config'])
        if deviceconfig['scan_type'] == "gsm":
            GSM(configurl, devicename, configid, deviceconfig['scan_band'])
    else:
        # Four interleaved scans
        print("interleaved scan")
        if deviceconfig['scan_type'] == "power":
            LimeScan(configurl, devicename, configid, deviceconfig['custom_config'])
        if deviceconfig['scan_type'] == "gsm":
            GSM(configurl, devicename, configid, deviceconfig['scan_band'])
        time.sleep(2)

        if deviceconfig['scan_type_1'] == "power":
            LimeScan(configurl, devicename, configid, deviceconfig['custom_config_1'])
        if deviceconfig['scan_type_1'] == "gsm":
            GSM(configurl, devicename, configid, deviceconfig['scan_band_1'])
        time.sleep(2)

        if deviceconfig['scan_type_2'] == "power":
            LimeScan(configurl, devicename, configid, deviceconfig['custom_config_2'])
        if deviceconfig['scan_type_2'] == "gsm":
            GSM(configurl, devicename, configid, deviceconfig['scan_band_2'])
        time.sleep(2)

        if deviceconfig['scan_type_3'] == "power":
            LimeScan(configurl, devicename, configid, deviceconfig['custom_config_3'])
        if deviceconfig['scan_type_3'] == "gsm":
            GSM(configurl, devicename, configid, deviceconfig['scan_band_3'])
        time.sleep(2)

    delta = time.time() - scan_schedule_start
    if scan_schedule_start is not 0 and delta < interval_seconds: 
        # Measure interval from scan start, so if the scan took a long time start immediately
        time.sleep(interval_seconds - delta)
    checkSchedule()

checkSchedule()