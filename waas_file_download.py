#!/usr/bin/env python
#########################################################################
# Gregory Camp
# grcamp@cisco.com
# waas_file_download
#
# Testing Summary:
#   Tested with FLEX 7500 WLCs show run-config output, but should work
#   with any Cisco WLC.
#
# Usage:
#   ./cmx_runconfig_csv.py wlc_show-run-config input.csv -outfile.csv
#   The best way to pull the WLC show run config is via file upload on
#   WLC.  Must be performed by CLI.
#   input.csv format: Site Name,Address,RSSI High Threshold,RSSI Low Threshold,Dwell Time in Minutes,Site Timezone
#
# Global Variables:
#    logger = Used for Debug output and script info
# #########################################################################

import re
import os
import logging
import copy
import argparse
import sys
import xlsxwriter
import json
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

# Method wait_for_prompt
#
# Input: None
# Output: None
# Parameters: None
#
# Return Value: -1 on error, 0 for successful discovery
#####################################################################
def wait_for_prompt(self, remote_conn, myLogFile, prompt = ">", timeout=10):
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

    # Return None
    return allOutput

# Method upload_config
#
# Input: None
# Output: None
# Parameters: None
#
# Return Value: -1 on error, 0 for successful discovery
#####################################################################
def upload_config(self, ipAddress, username, password, ftpUploadUser, ftpUploadPass, ftpUploadIP, ftpUploadPath, ftpUploadFile):
    # Declare variables
    returnVal = 0
    downloadAttempts = 0

    # Open Log File
    myLogFile = open(ipAddress + "_log.txt",'a')

    # Attempt to login to devices via SSH
    try:
        # Attempt Login
        remote_conn_pre = paramiko.SSHClient()
        # Bypass SSH Key accept policy
        remote_conn_pre.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Attempt to connection
        remote_conn_pre.connect(ipAddress,username=username,password=password,look_for_keys=False,allow_agent=False)
        # Log into WLC
        remote_conn = remote_conn_pre.invoke_shell()
        time.sleep(15)
        myOutput = remote_conn.recv(65535)
        myLogFile.write(myOutput)
        myLogFile.flush()
        
        # Check if user prompt appears
        if "User:" not in myOutput:
            myLogFile.close()
            remote_conn.close()
            return -1

        remote_conn.send(username)
        remote_conn.send("\n")
        time.sleep(1)
        myOutput = remote_conn.recv(65535)
        myLogFile.write(myOutput)
        myLogFile.flush()
        remote_conn.send(password)
        remote_conn.send("\n")
        time.sleep(15)
        myOutput = remote_conn.recv(65535)
        myLogFile.write(myOutput)
        myLogFile.flush()
        
        # Check if user prompt appears
        if ">" not in myOutput:
            myLogFile.close()
            remote_conn.close()
            return -2
        
        # Login successful
        logger.info("Logged into %s" % (ipAddress))
        
        # Clear transfer info
        remote_conn.send("clear transfer")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile, prompt="(y/n)")
        remote_conn.send("y")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        
        # Get current time
        ftpUploadFile = ipAddress + ".txt"
        
        # Set Upload FTP parameters
        remote_conn.send("transfer upload datatype run-config")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload mode ftp")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload serverip " + ftpUploadIP)
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload path " + ftpUploadPath)
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload filename " + ftpUploadFile)
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload username " + ftpUploadUser)
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        remote_conn.send("transfer upload password " + ftpUploadPass)
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        # Start FTP
        remote_conn.send("transfer upload start")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile, prompt="(y/N)")
        remote_conn.send("y")
        remote_conn.send("\n")
        
        # Wait for output
        myOutput = wait_for_prompt(remote_conn, myLogFile, timeout=60)

        if "File transfer operation completed successfully." in myOutput:
            # Set returnVal to good
            returnVal = 0
            # Config upload successful
            logger.info("Run-config upload successful for %s" % (ipAddress))
        else:
            # Set returnVal to -3 while waiting
            returnVal = -3
        
        # Clear transfer info
        remote_conn.send("clear transfer")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile, prompt="(y/n)")
        remote_conn.send("y")
        remote_conn.send("\n")
        wait_for_prompt(remote_conn, myLogFile)
        
        # Logout
        remote_conn.send("logout")
        remote_conn.send("\n")
        time.sleep(1)
        myOutput = remote_conn.recv(65535)
        myLogFile.write(myOutput)
        # If asked to save config select No
        if "(y/N)" in myOutput:
            remote_conn.send("N")
            remote_conn.send("\n")
            time.sleep(2)
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
  

#########################################################################
# Class WAE
#
# Container for networks
#########################################################################
class WAE:
    def __init__(self):
        self.ipAddress = ""
        self.username = ""
        self.password = ""
        self.ftpConfig = {}

# Method write_xlsx_report
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
def build_wae_list(waasList, ftpConfig, username, password, ftpUsername, ftpPassword):
    # Declare variables
    returnList = []
    
    logger.info("Building WAE List")
    
    # Build FTP Config
    myFtpConfig = {'username':ftpUsername, 'password':ftpPassword, 'filePath':str(ftpConfig['filePath']), 
    'fileName':str(ftpConfig['fileName']), 'serverIP':str(ftpConfig['serverIP']), 'md5':str(ftpConfig['md5'])}
    
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
    

    logger.info("Starting worker for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount))
    i = device.download_image(myDeviceNum)

    # If discovered, parse data
    if i == 0:
        logger.info("Image Download Complete for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount))
        return None
    # Else printer error
    elif i == -2:
        logger.info("Bad username or password for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount))
    elif i == -3:
        logger.info("Image Download Failed for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount))
    else:
        logger.info("Image Download Failed for %s - %s of %s" % (str(device.ipAddress), str(myDeviceNum), str(deviceCount))

    return None


# Method main
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
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(asctime)s [%(levelname)8s]:  %(message)s")

    if kwargs:
        args = kwargs
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument('waasList', help='WAAS IP List')
        parser.add_argument('ftpConfig', help='FTP Config')
        parser.add_argument('-u', '--username', help='WAAS Username')
        parser.add_argument('-p', '--password', help='WAAS Password')
        parser.add_argument('-U', '--ftpUsername', help='FTP Username')
        parser.add_argument('-P', '--ftpPassword', help='FTP Password')

        args = parser.parse_args()

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
    myWAEs = build_wae_list(waasList, ftpConfig, args.username, args.password, args.ftpUsername, args.ftpPassword)
    
    # Set Device count
    deviceCount = len(myWAEs)
    
    # Build Thread Pool
    pool = ThreadPool(WORKER_COUNT)
    # Launch worker
    results = pool.map(download_image_worker, myWAEs)

    # Wait for all threads to complete
    pool.close()
    pool.join()

    return None


if __name__ == '__main__':
    try:
        main()
    except Exception, e:
        print str(e)
        os._exit(1)
