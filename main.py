#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import os
import urllib2
import base64
import json
import urlparse
import time
from datetime import datetime
from argparse import ArgumentParser

def prepareLog():
    global logFile
    logFilePath = scriptPath + '/gfwlist2dnsmasq.log'

    # The maximum log file size is 128 KB;
    maxSize     = 128 * 1000;

    if os.path.exists(logFilePath) and os.path.getsize(logFilePath) < maxSize:
        logFileMode = 'a'
    else:
        logFileMode = 'w'

    logFile = open(logFilePath, logFileMode)

def message(msg, log=True, separation=False):
    if not separation:
        print msg

    if not log:
        return

    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not separation:
        logFile.write('[%(now)s] %(message)s \n' % {'now': now, 'message': msg})
    else:
        logFile.write('%(message)s \n' % {'message': msg})

def getRootNameList(domainList):
    tldList    = getTldList()

    # Why use `set`? because it also will remove duplicates rules from list:
    # https://docs.python.org/2/library/sets.html
    resultList = set()

    for domain in domainList:
        domainParts = domain.split('.')
        rootDomain = None
        for i in xrange(0, len(domainParts)):
            part = '.'.join(domainParts[len(domainParts) - i - 1:])

            if i == 0 and not part in tldList:
                break;

            if not part in tldList:
                rootDomain = part
                break

        if rootDomain:
            resultList.add(rootDomain)

    return list(resultList)

def getHostname(hostList):
    hostnameList = []

    for host in hostList:
        if not host.startswith('http'):
            host = 'http://' +  host

        try:
            parsed = urlparse.urlparse(host)
            if parsed.netloc:
                hostnameList[len(hostnameList):] = [parsed.netloc]
        except:
            pass

    return hostnameList

def getTldList():
    tldList = []

    with open( scriptPath + '/resources/public_suffix_list.dat') as tldFile:
        for tld in tldFile:
            tld = tld.strip()
            if tld and not tld.startswith('//'):
                tldList[len(tldList):] = [tld]

    return tldList

def getList(path, isGFWList=False):

    if os.path.isfile(path):

        # The list is from local.
        message('Getting list from: ' + path + ' ...')

        with open(path) as localList:
            rawGfwList = localList.read()

    elif urlparse.urlparse(path).scheme:

        # The list is from internet.
        try:
            message('Downloading list from: ' + path + ' ...')
            rawGfwList = urllib2.urlopen(path, timeout = 10).read()
        except Exception, e:
            message('Download list failed: ' + str(e))
            sys.exit(1)

    else:
        message('Invalid file:' + path)
        return

    result  = {
        'updateTime': None,
        'src'       : path,
        'length'    : None,
        'list'      : []
    }

    # The GFWList is base64 encoded string
    if isGFWList:
        gfwList = base64.b64decode(rawGfwList).splitlines()
    else:
        gfwList = rawGfwList.splitlines()

    # Parse list
    for line in gfwList:

        if line.find('Last Modified') >= 0:
            result['updateTime'] = line.replace('! Last Modified:', '')

        elif line.startswith('!'):
            # Starts with `!` means it's a comment
            continue

        elif not line:
            # Empty string
            continue

        elif line.startswith('@@||'):
            # White list
            continue

        elif line.startswith('@@|http'):
            result['list'].append(line.replace('@@|', '', 1))

        elif line.startswith('.'):
            result['list'].append(line.replace('.', '', 1))

        elif line.startswith('||'):
            result['list'].append(line.replace('||', '', 1))

        elif line.startswith('|'):
            result['list'].append(line.replace('|', '', 1))

        else:
            result['list'].append(line)

    result['length'] = len(result['list'])

    message('Got ' + str(result['length']) + ' rules from: ' + path)

    return result

def runCallback(command):
    message('Running command: ' + command + '...')

    if os.system(command) == 0:
        message(command + ' succeeded')
    else:
        message(command + ' failed')

def generatingConfigFile(allList, config):
    message('Generating config file...')

    now    = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    header = '\n'.join([
        '# Generated by gfwlist2dnsmasq at: %(now)s\n' % {'now': now},
        ''
    ])

    listHeader = '\n'.join([
        '# From: %(src)s',
        '# Last Modified at: %(updateTime)s',
        '# Generated %(length)s rules',
        '\n'
    ])

    itemTemplate = '\n'.join([
        'server=/%(domain)s/' + config['dnsServer'] + '#' + str(config['dnsPort']),
        'ipset=/%(domain)s/' + config['ipsetName'],
        '\n'
    ])

    with open(config['targetFile'], 'w') as configFile:
        configFile.write(header)

        for listItem in allList:
            configFile.write(listHeader % listItem)
            for item in listItem['list']:
                configFile.write(itemTemplate % {'domain': item})

        message('Generated config file to ' + config['targetFile'])

def perpreArgs():
    parser = ArgumentParser()

    parser.add_argument('-c', '--config', dest='config',
                        help='Specifically usea configuration file.' +
                             'You can check the README file to know how to' +
                             'create a config file.')

    return parser.parse_args()

def getConfig(args):
    userConfig = {};
    configKeys = ['sourceUrl', 'dnsServer', 'dnsPort', 'userList', 'ipsetName',
                  'targetFile', 'callbackCommand']

    if args.config:
        try:
            with open(args.config) as userConfig:
                userConfig = json.loads( userConfig.read() )

        except Exception, e:
            message('Unable to open config file: ' + str(e))
            sys.exit(1)

    with open(scriptPath + '/resources/default-config.json') as defaultConfig:
        defaultConfig = json.loads( defaultConfig.read() )

        defaultConfig['targetFile'] = scriptPath +  '/' + defaultConfig['targetFile']


    for configKey in configKeys:
        if configKey not in userConfig.keys() and configKey in defaultConfig.keys() and defaultConfig[configKey]:

            userConfig[configKey] = defaultConfig[configKey]

        elif configKey not in userConfig.keys() and configKey not in defaultConfig.keys():

            userConfig[configKey] = None

    return userConfig

def main():
    global scriptPath

    allList    = []
    args       = perpreArgs()
    scriptPath = os.path.dirname(os.path.realpath(__file__))

    prepareLog()

    if args.config == None:
        message('Starting with default config. You can specific configuration file by using -c/--config')
    else:
        message('Starting with the config file: ' + args.config)

    configurations = getConfig(args)

    # Getting list from GFWList
    gfwList = getList(configurations['sourceUrl'], True)
    gfwList['list'] = getHostname(gfwList['list'])
    gfwList['list'] = getRootNameList(gfwList['list'])

    if len(gfwList['list']) == 0:
        message('ERROR: The GFWList is empty')
        sys.exit(1)

    allList[len(allList):] = [gfwList]

    # Getting list from extends file
    extendsList = getList(scriptPath + '/resources/extends.txt')
    extendsList['list'] = getHostname(extendsList['list'])
    extendsList['list'] = getRootNameList(extendsList['list'])

    allList[len(extendsList):] = [extendsList]

    # Getting user list
    if 'userList' in configurations and configurations['userList']:
        userListPath = configurations['userList'].split('|')

        for path in userListPath:
            userListItem = getList(path)
            userListItem['list'] = getHostname(userListItem['list'])

            allList[len(allList):] = [userListItem]

    # Generating config file
    generatingConfigFile(allList, configurations)

    # Run callback command if has
    if configurations['callbackCommand']:
        runCallback(configurations['callbackCommand'])

    # Add a new empty line, make the log easy to read
    message('', True, True)

    # Closing log file
    logFile.close()

if __name__ == '__main__':
    main()
