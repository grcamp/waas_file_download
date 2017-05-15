#!/usr/bin/env python
#########################################################################
# Gregory Camp
# grcamp@cisco.com
# waas_file_download
#
# Testing Summary:
#   Tested on WAE 294 appliances running 5.5.9-b10
#
# Usage:
#   ./waas_file_download.py waas_list.txt ftp_config.json -u username -p password
#
# Global Variables:
#   logger = Used for Debug output and script info
#   WORKER_COUNT = Maximum number of simultaneous threads
#   currentDevice = Used for tracking the active device threads
#   deviceCount = Used for tracking total device threads
##########################################################################

import os
import logging
import time
import argparse
import paramiko
import sys
import xlsxwriter
import json
import socket
import getpass
from multiprocessing.dummy import Pool as ThreadPool

# Declare global variables
logger = logging.getLogger(__name__)
WORKER_COUNT = 25
currentDevice = 0
deviceCount = 0

def warning(msg):
    logger.warning(msg)


def error(msg):
    logger.error(msg)


def fatal(msg):
    logger.fatal(msg)
    exit(1)


#########################################################################
# Class WAE
#
# Container for WAAS appliances
#########################################################################
class WAE:
    def __init__(self):
        self.ipAddress = ""
        self.hostname = ""
        self.username = ""
        self.password = ""
        self.ftpConfig = {}
        self.downloadComplete = False

    # Method download_image
    #
    # Input: None
    # Output: None
    # Parameters: None
    #
    # Return Value: -1 on error, 0 for successful discovery
    #####################################################################
    def download_image(self, deviceNumber):
        # Declare variables
        returnVal = 0

        # Open Log File
        myLogFile = open(self.ipAddress + "_log.txt", 'a')

        # Attempt to login to devices via SSH
        try:
            # Attempt Login
            remote_conn_pre = paramiko.SSHClient()
            # Bypass SSH Key accept policy
            remote_conn_pre.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Attempt to connection
            remote_conn_pre.connect(self.ipAddress, username=self.username, password=self.password, look_for_keys=False,
                                    allow_agent=False)
            # Log into WAE
            remote_conn = remote_conn_pre.invoke_shell()
            time.sleep(15)
            myOutput = remote_conn.recv(65535)
            myLogFile.write(myOutput)
            myLogFile.flush()

            # Check if user prompt appears
            if "#" not in myOutput:
                # if not exit method
                myLogFile.close()
                remote_conn.close()
                return -2

            # Login successful
            logger.info("Logged into %s - %s of %s" % (self.ipAddress, str(deviceNumber), str(deviceCount)))

            # Obtain hostname for prompts
            remote_conn.send("show run | i hostn")
            remote_conn.send("\n")
            myOutput = self._wait_for_prompt(remote_conn, myLogFile)

            lines = myOutput.split("\n")

            # Search through output for hostname
            for line in lines:
                if "hostname" in line:
                    self.hostname = line.strip().split()[1]

            # Login successful
            logger.info("Hostname for %s is %s - %s of %s" % (self.ipAddress, self.hostname, str(deviceNumber), str(deviceCount)))

            # Start FTP transfer
            remote_conn.send("copy ftp disk %s %s %s %s" % (self.ftpConfig['serverIP'], self.ftpConfig['filePath'],
                                                            self.ftpConfig['fileName'], self.ftpConfig['fileName']))
            remote_conn.send("\n")
            # Send login information
            myOutput = self._wait_for_prompt(remote_conn, myLogFile, prompt="server:")
            print(myOutput)
            if "already exists" not in myOutput:
                remote_conn.send(self.ftpConfig['username'])
                remote_conn.send("\n")
                self._wait_for_prompt(remote_conn, myLogFile, prompt="server:")
                remote_conn.send(self.ftpConfig['password'])
                remote_conn.send("\n")
                self._wait_for_prompt(remote_conn, myLogFile)
                self._wait_for_prompt(remote_conn, myLogFile, prompt=(self.hostname + "#"), timeout=21600)

            # Verify File
            remote_conn.send("md5sum %s" % (self.ftpConfig['fileName']))
            remote_conn.send("\n")
            myOutput = self._wait_for_prompt(remote_conn, myLogFile, prompt=(self.hostname + "#"), timeout=60)

            if self.ftpConfig['md5'] in myOutput:
                returnVal = 0
                self.downloadComplete = True
            else:
                returnVal = -3

            # Logout
            remote_conn.send("exit")
            remote_conn.send("\n")
            time.sleep(1)
            myOutput = remote_conn.recv(65535)
            myLogFile.write(myOutput)

            # Close connection
            remote_conn.close()
            myLogFile.close()
        # Print exception and return -1
        except IOError as error:
            print("Invalid Hostname")
            myLogFile.close()
            return -1
        except paramiko.PasswordRequiredException as error:
            print("Invalid Username or password")
            myLogFile.close()
            return -2
        except paramiko.AuthenticationException as error:
            print("Invalid Username or password")
            myLogFile.close()
            return -2
        except socket.timeout as error:
            print("Connection timeout")
            myLogFile.close()
            return -1
        except Exception, e:
            print(str(e))
            myLogFile.close()
            return -1

        # Return success
        return returnVal

    # Method _wait_for_prompt
    #
    # Input: None
    # Output: None
    # Parameters: None
    #
    # Return Value: -1 on error, 0 for successful discovery
    #####################################################################
    def _wait_for_prompt(self, remote_conn, myLogFile, prompt="#", timeout=10):
        # Declare variables
        myOutput = ""
        allOutput = ""
        i = 0

        # Wait timeout seconds total
        while i < timeout:
            time.sleep(1)
            myOutput = remote_conn.recv(65535)
            allOutput = allOutput + myOutput

            if prompt in myOutput:
                i = timeout

            myLogFile.write(myOutput)
            myLogFile.flush()
            i = i + 1
            print(str(i) + "," + str(timeout))

        # Return None
        return allOutput



# function write_xlsx_report
#
# Input: None
# Output: None
# Parameters: None
#
# Return Value: None
#####################################################################
def write_xlsx_report(flexGroupList, apList, outputFile):
    # Log state
    logger.info("Writing Report to %s" % (outputFile))

    # Build workbook and initialize worksheet
    workbook = xlsxwriter.Workbook(outputFile)
    worksheet = workbook.add_worksheet("FlexConnect Group Summary")

    # Set headers
    headingCellFormat = workbook.add_format({'bold': True, 'border': 1})
    dataCellFormat = workbook.add_format({'border': 1})

    # Set heading and initialize row and column variables
    heading = ["Group Name", "Efficient Upgrade", "Joined Masters", "Disconnected Masters", "Joined APs",
               "Disconnected APs", "Total APs"]

    # Initialize row and col
    row = 0
    col = 0

    # Write header and freeze top row
    worksheet.write_row(row, col, heading, headingCellFormat)
    worksheet.freeze_panes(1,0)

    for group in flexGroupList:
        row += 1
        worksheet.write_row(row, col, group.get_xlsx_summary_list())

    workbook.close()

    # Return None
    return None

# Method build_wae_list
#
# Input: None
# Output: None
# Parameters: None
#
# Return Value: None
#####################################################################
def build_wae_list(waasList, ftpConfig, username, password):
    # Declare variables
    returnList = []
    
    logger.info("Building WAE List")
    
    # Build FTP Config
    myFtpConfig = {'username':str(ftpConfig['username']), 'password':str(ftpConfig['password']),
                   'filePath':str(ftpConfig['filePath']), 'fileName':str(ftpConfig['fileName']),
                   'serverIP':str(ftpConfig['serverIP']), 'md5':str(ftpConfig['md5'])}
    
    # Get configuration for each flex-connect group
    for line in waasList:
        if line.strip() != "":
            myWAE = WAE()
            myWAE.ipAddress = line.strip()
            myWAE.username = username
            myWAE.password = password
            myWAE.ftpConfig = myFtpConfig.copy()
            returnList.append(myWAE)

    # Return None
    return returnList

# Method download_image_worker
#
# Input: None
# Output: None
# Parameters: string the_list, string subString
#
# Return Value: -1 of error, index of first occurrence if found
#####################################################################
def download_image_worker(device):
    # Declare variables
    global currentDevice
    global deviceCount
    currentDevice = currentDevice + 1
    myDeviceNum = long(currentDevice)
    

    logger.info("Starting worker for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount)))
    i = device.download_image(currentDevice)

    # If discovered, parse data
    if i == 0:
        logger.info("Image Download Complete for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount)))
        return None
    # Else print error
    elif i == -2:
        logger.info("Bad username or password for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount)))
    elif i == -3:
        logger.info("Image Download Failed for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount)))
    else:
        logger.info("Image Download Failed for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount)))

    return None


# Function main
#
# Input: None
# Output: None
# Parameters: None
#
# Return Value: None
#####################################################################
def main(**kwargs):
    # Declare variables
    myWAEs = []
    global deviceCount

    # Set logging
    global headers
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)8s]:  %(message)s")

    if kwargs:
        args = kwargs
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument('waasList', help='WAAS IP List')
        parser.add_argument('ftpConfig', help='FTP Config')
        parser.add_argument('-u', '--username', help='WAAS Username')
        parser.add_argument('-p', '--password', help='WAAS Password')
        parser.add_argument('-r', '--report', help='CSV Report')

        args = parser.parse_args()

    # Check for username input
    if args.username == None:
        args.username = raw_input("Username: ")
    # Check for password input
    if args.password == None:
        args.password = getpass.getpass()
    # Check for report input
    if args.report == None:
        args.report = "report.csv"



    # Open file
    myFile = open(args.waasList, 'r')
    # Read file into a list
    waasList = [i for i in myFile]
    # Close file
    myFile.close()
    
    # Log info
    logger.info("WAAS List Imported")
    
    # Open file
    myFile = open(args.ftpConfig, 'r')
    # Read file into a list
    ftpConfig = json.load(myFile)
    # Close file
    myFile.close()
    
    # Log info
    logger.info("FTP Config Imported")
    
    # Build WAE List
    myWAEs = build_wae_list(waasList, ftpConfig, args.username, args.password)
    
    # Set Device count
    deviceCount = len(myWAEs)
    
    # Build Thread Pool
    pool = ThreadPool(WORKER_COUNT)
    # Launch worker
    results = pool.map(download_image_worker, myWAEs)

    # Wait for all threads to complete
    pool.close()
    pool.join()

    # Log info
    logger.info("Writing report to %s" % (args.report))

    # Open file
    with open(args.report, 'w') as reportFile:
        # Print Header
        reportFile.write("Name,IP Address,Download Complete\n")
        # Print status of each WAE download
        for myWAE in myWAEs:
            reportFile.write("%s,%s,%s\n" % (myWAE.hostname, myWAE.ipAddress, str(myWAE.downloadComplete)))

    reportFile.close()

    return None


if __name__ == '__main__':
    try:
        main()
    except Exception, e:
        print str(e)
        os._exit(1)
