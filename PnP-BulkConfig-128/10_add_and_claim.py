#!/usr/bin/env python
from __future__ import print_function
import csv
import json
import requests
import os
import os.path
import logging
from argparse import ArgumentParser
from utils import login, get, post

logger = logging.getLogger()

class SiteCache:
    def __init__(self, dnac):
        self._cache = {}
        response = get(dnac, "group?groupType=SITE")
        sites = response.json()['response']
        for s in sites:
            self._cache[s['groupNameHierarchy']] =  s['id']
    def lookup(self, fqSiteName):
        if fqSiteName in self._cache:
            return self._cache[fqSiteName]
        else:
            raise ValueError("Cannot find site:{}".format(fqSiteName))

def add_device(dnac, name, serial, pid):
    payload = [{
	"deviceInfo": {
		"name": name,
		"serialNumber": serial,
		"pid": pid,
		"sudiRequired": False,
		"userSudiSerialNos": [],
		"stack": False,
		"aaaCredentials": {
			"username": "",
			"password": ""
		}
	}
}]
    device = post(dnac, "onboarding/pnp-device/import", payload)
    try:
        deviceId = device.json()['successList'][0]['id']
    except IndexError as e:
        print ('##SKIPPING device:{},{}:{}'.format(name, serial, device.json()['failureList'][0]['msg']))
        deviceId = None

    return deviceId

# other options.
# type="stackSwitch"
# "licenseLevel":"",
# "topOfStackSerialNumber":"",
def claim_device(dnac,deviceId, configId, siteId, params):
    payload = {
        "siteId": siteId,
         "deviceId": deviceId,
         "type": "Default",
         "imageInfo": {"imageId": "", "skip": False},
         "configInfo": {"configId": configId, "configParameters": params}
}
    #print json.dumps(payload, indent=2)

    claim = post(dnac,"onboarding/pnp-device/site-claim", payload)

    return claim.json()['response']

def find_template_name(data, templateName):
    for attr in data:
        if 'key' in attr:
            if attr['key'] == 'day0.templates':
                for dev in attr['attribs']:
                    # DeviceFamily/DeviceSeries/DeviceType
                    template = dev['attribs'][0]['attribs'][0]['attribs'][0]
                    if template['attribs'][1]['value'] == templateName:
                       return template['value']
    raise ValueError("Cannot find template named:{}".format(templateName))

def find_site_template(dnac, siteId, templateName):
    response = get(dnac,"siteprofile/site/{}".format(siteId))
    if response.json()['response'] == []:
        raise ValueError("Cannot find Network profile for siteId:{}".format(siteId))

    # now need to find the template
    data = response.json()['response'][0]['profileAttributes']
    return find_template_name(data, templateName)


def get_template(dnac, configId, supplied_params):
    params=[]
    response = get(dnac, "template-programmer/template/{}".format(configId))
    for vars in response.json()['templateParams']:
        name = vars['parameterName']
        params.append({"key": name, "value": supplied_params[name]})
    #print params
    return params

def create_and_upload(dnac, site_cache, devices):

    f = open(devices, 'rt')
    try:
        reader = csv.DictReader(f)
        for device_row in reader:
            #print ("Variables:",device_row)

            try:
                siteId = site_cache.lookup(device_row['siteName'])

            except ValueError as e:
                print("##ERROR {},{}: {}".format(device_row['name'],device_row['serial'], e))
                continue
            # need to get templateId from Site..
            configId = find_site_template(dnac, siteId, device_row['templateName'])
            params = get_template(dnac, configId, device_row)

            deviceId = add_device(dnac, device_row['name'], device_row['serial'], device_row['pid'])
            if deviceId is not None:
                #claim
                claim_status = claim_device(dnac, deviceId, configId, siteId, params)
                if "Claimed" in claim_status:
                    status = "PLANNED"
                else:
                    status = "FAILED"
                print ('Device:{} name:{} siteName:{} Status:{}'.format(device_row['serial'],
                                                                    device_row['name'],
                                                                    device_row['siteName'],
                                                                    status))
    finally:
        f.close()

if __name__ == "__main__":
    parser = ArgumentParser(description='Select options.')
    parser.add_argument( 'devices', type=str,
            help='device inventory csv file')
    parser.add_argument('-v', action='store_true',
                        help="verbose")
    args = parser.parse_args()

    if args.v:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # set logger
    logger.debug("Logging enabled")
    dnac = login()
    site_cache = SiteCache(dnac)


    print ("Using device file:", args.devices)

    print ("##########################")
    create_and_upload(dnac, site_cache, devices=args.devices)
