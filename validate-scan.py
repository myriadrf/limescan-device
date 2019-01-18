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
import argparse
from termcolor import colored

def getDigest(input):
    block_size = 65536
    sha256 = hashlib.sha256()
    sha256.update(input.encode('utf-8'))
    digest = sha256.hexdigest()
    return(digest)


def limescanNanoseconds(timestamp):
    dot_index = timestamp.index('.') + 4 # strptime doesn't handle nanoseconds well so this adds them on at the end
    timestamp_extra_digits =  "00" + str(timestamp[dot_index:-1]) # extra two digits to count for the increment required for storing limescan
    timestamp_obj = datetime.strptime(timestamp[:dot_index], '%Y-%m-%dT%H:%M:%S.%f')
    nanoseconds = str(str(timestamp_obj.timestamp()).replace(".","") + timestamp_extra_digits)
    return nanoseconds.ljust(19, "0")


def validateScan(scanid, digest):
    scan = json.loads(requests.post(configurl + "scans/data/", json={ "scanid": scanid }).text)
    if scan["results"][0].get("series") is None:
        return False

    values = scan["results"][0]["series"][0]["values"]
    tags = scan["results"][0]["series"][0]["tags"]
    if tags["ARFCN"] is not '' and tags["ARFCN"] is not None:
        # The scan type is GSM
        values = values[0]
        timestamp = values[0]
        dot_index = timestamp.index('.') + 4 # strptime doesn't handle nanoseconds well so this adds them on at the end
        timestamp_extra_digits = str(timestamp[dot_index:-1])
        timestamp_obj = datetime.strptime(timestamp[:dot_index], '%Y-%m-%dT%H:%M:%S.%f')
        nanoseconds = str(timestamp_obj.timestamp()).replace(".","") + timestamp_extra_digits
        influxline = "gsm,sensor=" + tags["sensor"] + ",ARFCN=" + tags["ARFCN"] + ",CID=" + tags["CID"] + ",LAC=" + tags["LAC"] + ",MCC=" + tags["MCC"] + ",MNC=" + tags["MNC"] + ",band=" + tags["band"] + " Pwr=" + str(values[1]) + " " + nanoseconds.ljust(19, "0")
        scan_digest =  getDigest(influxline)
    else:
        # The scan type is Power 
        lines = ""
        values = scan["results"][0]["series"][0]["values"]
        values.sort(key=lambda x:limescanNanoseconds(x[0]))
        for row in values:
            timestamp = row[0]
            nanoseconds = limescanNanoseconds(timestamp)
            influxline = "power,sensor=" + tags["sensor"] + " hzlow=" + str(row[4]) + ",hzhigh=" + str(row[3]) + ",step=" + str(row[7]) + ",samples=3,dbs=\"" + row[2] + "\" " + nanoseconds
            lines += '\n' + influxline
        scan_digest = getDigest(lines)
    if scan_digest == digest:
        return True
    else:
        return False

def validateMetadata(metadata):
    metadata["scan_start_time"] = float(metadata["scan_start_time"])
    metadata["scan_finish_time"] = float(metadata["scan_finish_time"])
    return getDigest(json.dumps(metadata, sort_keys=True)) == scanid

config = configparser.ConfigParser()
configfile = config.read('config.ini')
if len(configfile) == 0:
    raise ValueError("Configuration file missing, rename config.example.ini to config.ini")

parser = argparse.ArgumentParser()
parser.add_argument("--scanid", help="Get data by scanid")
args = parser.parse_args()

configurl = config["DEFAULT"]["API_URL"]
url = config["DEFAULT"]["DATA_URL"] + "query?db=limescan"

scanid = ""

if args.scanid:
    if len(args.scanid) == 7:
        shortid = args.scanid
        scanid = json.loads(requests.get(configurl + "scans/fullid/" + shortid).text)["id"]
    else:
        scanid = args.scanid

request = requests.get(configurl + "scans/metadata/" + scanid)
if request.status_code == 404:
    print("Scan ID does not exist or is not valid")
else:
    metadata = json.loads(request.text)

    isMetadataValid = validateMetadata(metadata)
    isScanDataValid = validateScan(scanid, metadata["scan_digest"])
    if isMetadataValid:
        print(colored("Metadata digest valid", 'green'))
    else:
        print(colored("Metadata digest invalid", 'red'))

    if isScanDataValid:
        print(colored("Data digest valid", 'green'))
    else:
        print(colored("Data digest invalid", 'red'))