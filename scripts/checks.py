#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
import subprocess, os, sys
import urllib
import urllib2
import json
import argparse
import numpy as np

def check_download(obsID, directory=None, required_size=253440000):
    '''
    Checks that the number of files in directory (default is /scratch2/mwaops/vcs/[obsID]/raw/) is the same
    as that found on the archive and also checks that all files have the same size (253440000 by default).
    '''
    if not directory:
        directory = "/scratch2/mwaops/vcs/{0}/raw/".format(obsID)
    print "\n Checking file size and number of files for obsID {0} in {1}".format(obsID, directory)
    required_size = required_size
    command = "ls -ltr %s | awk '($5!=%s){print \"file \" $9 \" has size \" $5}'" %(directory, required_size)
    output = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True).communicate()[0]
    obsinfo = getmeta(service='obs', params={'obs_id':obsID})
    files = obsinfo['files']
    # assuming all files we want have .dat ending, we count how many there are,
    # recently .fits files were added messing up the number count somewhat
    files_on_archive = ['.dat' in file for file in files.keys()].count(True)
    files_in_dir = int(subprocess.Popen(["ls {0} | wc -l".format(directory)], \
                                                   shell=True, stdout=subprocess.PIPE).communicate()[0])
    success = True
    if not files_in_dir == files_on_archive:
        print "We have {0} files but expected {1}".format(files_in_dir, files_on_archive)
        success = False
    if len(output) > 16:
        print output[16:]
        success = False
    return success

def check_recombine(obsID, directory=None, required_size=327680000, \
                        required_size_ics=30720000):
    '''
    Checks that the number of files in directory (/scratch2/mwaops/vcs/[obsID]/combined/) is ....
    as that found on the archive and also checks that all files have the same size (327680000 by default).
    '''
    if not directory:
        directory = "/scratch2/mwaops/vcs/{0}/combined/".format(obsID)
    print "\n Checking file size and number of files for obsID {0} in {1}".format(obsID, directory)
    required_size = required_size
    output = subprocess.Popen(["ls -ltr %s*ch*.dat | awk '($5!=%s){print \"file \" $9 \" has size \" $5}'" %(directory, required_size)],
                              stdout=subprocess.PIPE, shell=True).communicate()[0]
    # we need to get the number of unique seconds from the file names
    files = np.array(getmeta(service='obs', params={'obs_id':obsID})['files'].keys())
    mask = np.array(['.dat' in file for file in files])
    times = [time[11:21] for time in files[mask]]
    n_secs = len(set(times))
    expected_files = n_secs * 25
    files_in_dir = int(subprocess.Popen(["ls {0} | wc -l".format(directory)], \
                                                   stdout=subprocess.PIPE, shell=True).communicate()[0])
    success = True
    if not files_in_dir == expected_files:
        print "We have {0} files but expected {1}".format(files_in_dir, expected_files)
        success = False
    if len(output) > 16:
        print output[16:]
        success = False
    success = check_recombine_ics(directory=directory, \
                                      required_size=required_size_ics)
    return success

def check_recombine_ics(directory=None, required_size=30720000):
    required_size = required_size
    output = subprocess.Popen(["ls -ltr %s/*ics.dat | awk '($5!=%s){print \"file \" $9 \" has size \" $5}'" %(directory, required_size)],
                              stdout=subprocess.PIPE, shell=True).communicate()[0]
    success = True
    if len(output) > 16:
        print output[16:]
        success = False
    return success

# Append the service name to this base URL, eg 'con', 'obs', etc.
BASEURL = 'http://mwa-metadata01.pawsey.org.au/metadata/'


def getmeta(service='obs', params=None):
  """
  Function to call a JSON web service and return a dictionary:
  Given a JSON web service ('obs', find, or 'con') and a set of parameters as
  a Python dictionary, return a Python dictionary containing the result.
  Taken verbatim from http://mwa-lfd.haystack.mit.edu/twiki/bin/view/Main/MetaDataWeb
  """

  if params:
    data = urllib.urlencode(params)  # Turn the dictionary into a string with encoded 'name=value' pairs
  else:
    data = ''

  if service.strip().lower() in ['obs', 'find', 'con']:
    service = service.strip().lower()
  else:
    print "invalid service name: %s" % service
    return

  try:
    result = json.load(urllib2.urlopen(BASEURL + service + '?' + data))
  except urllib2.HTTPError as error:
    print "HTTP error from server: code=%d, response:\n %s" % (error.code, error.read())
    return
  except urllib2.URLError as error:
    print "URL or network error: %s" % error.reason
    return

  return result

def opt_parser():
    parser=argparse.ArgumentParser(description="scripts to check sanity of downloads and recombine.")
    parser.add_argument("-m", "--mode", type=str, choices=['download','recombine'],\
                          help="Mode you want to run: download, recombine", required=True,
                        dest='mode')
    parser.add_argument("-o", "--obs", metavar="OBS ID", type=int, dest='obsID',\
                            help="Observation ID you want to process [no default]",\
                            required=True)
    parser.add_argument("-s", "--size", type=int, dest='size',\
                          help="The files size in bytes that you expect all files" +\
                          " to have. Defaults are 253440000 (download), 327680000" +\
                          " (recombined, not ics)")
    parser.add_argument("-S", "--size_ics", type=int, help='Size in bytes that' +\
                            "you expect the ics files to have. Default = %(default)s",\
                            dest='size_ics', default=30720000)
    parser.add_argument('-w', '--work_dir', type=str, dest='work_dir',\
                            help="Directory " + \
                            "to check the files in. Default is /scratch2/mwaops/vcs/" + \
                            "[obsID]/[raw,combined]")
    return parser.parse_args()

if __name__ == '__main__':
    args = opt_parser()
    work_dir_base = '/scratch2/mwaops/vcs/' + str(args.obsID)

    if args.mode == 'download':
        required_size = 253440000
        if args.size:
            required_size = args.size
        work_dir = work_dir_base + '/raw/'
        if args.work_dir:
            work_dir = args.work_dir
        check_download(args.obsID, directory=work_dir, required_size=required_size)

    elif args.mode == 'recombine':
        required_size = 327680000
        if args.size:
            required_size = args.size
        required_size_ics = args.size_ics
        work_dir = work_dir_base + '/combined/'
        if args.work_dir:
            work_dir = args.work_dir
        check_recombine(args.obsID, directory=work_dir, required_size=required_size, \
                            required_size_ics=required_size_ics)
    else:
        print "No idea what you want to do. This mode is not supported. Ckeck the help."
        sys.exit()
