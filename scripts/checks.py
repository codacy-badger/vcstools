#!/usr/bin/env python
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import subprocess, os, sys
import urllib
import urllib2
import json
import argparse
import numpy as np
import traceback

def check_download(obsID, directory=None, startsec=None, n_secs=None, data_type='raw'):
    '''
    Checks that the number of files in directory (default is /astro/mwaops/vcs/[obsID]/raw/) is the same
    as that found on the archive and also checks that all files have the same size (253440000 for raw, 7864340480 for recombined tarballs by default).
    '''
    if not data_type in ['raw', 'tar_ics', 'ics']:
        print "Wrong data type given to download check."
        return True
    if not directory:
        directory = "/astro/mwaops/vcs/{0}/raw/".format(obsID) if data_type == 'raw' else "/astro/mwaops/vcs/{0}/combined/".format(obsID)
    base = "\n Checking file size and number of files for obsID {0} in {1} for ".format(obsID, directory)
    n_secs = n_secs if n_secs else 1
    print base + "gps times {0} to {1}".format(startsec, startsec+n_secs-1) if startsec else base + "the whole time range."

    # put files in
    try:
        files, suffix, required_size = get_files_and_sizes(obsID, data_type)
    except:
        return True

    if not startsec:
        n_files_expected = len(files)
        command = "ls -l %s/*%s | ((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | " %(directory, suffix) + \
            "awk '($5!=%s){print \"file \" $9 \" has size \" $5 \" (expected %s)\"}' >> %s/%s_all.txt) 4>&1;" %(required_size, required_size,directory, obsID) + \
            "cat %s/%s_all.txt; rm -rf %s/%s_all.txt" %(directory, obsID, directory, obsID)
        output = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True).stdout
    else:
        n_files_expected = 0
        times = [int(time[11:21]) for time in files]
        for sec in range(startsec,startsec+n_secs):
            n_files_expected += times.count(sec)
        output = subprocess.Popen(["count=0;for sec in `seq -w %s %s `;do let count=${count}+`ls -l %s/*${sec}*%s | " %(startsec, startsec+n_secs-1, directory, suffix) + \
                                       "((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | awk '($5!=%s) " %(required_size) + \
                                       "{print \"file \" $9 \" has size \" $5 \" (expected %s)\"}' >> %s/errors_%s.txt) 4>&1`;done;" %(required_size,directory,startsec) +\
                                       "echo ${count}; cat %s/errors_%s.txt;rm -rf %s/errors_%s.txt" %(directory,startsec,directory,startsec)],
                                  stdout=subprocess.PIPE, shell=True).stdout
    output = output.readlines()
    files_in_dir = int(output[0].strip())

    error = False

    # in case we're checking for downloaded tarballs also need to check ics-files.
    if data_type == 'tar_ics':
        print "Now checking ICS files"
        error, n_ics = check_recombine_ics(directory=directory, \
                                               startsec=startsec, n_secs=n_files_expected, obsID=obsID)
        n_files_expected *= 2
        files_in_dir += n_ics


    if not files_in_dir == n_files_expected:
        print "We have {0} files but expected {1}".format(files_in_dir, n_files_expected)
        error = True
    for line in output[1:]:
        if 'file' in line:
            print line
            error = True
    if not error:
        print "We have all {0} {1} files as expected.".format(files_in_dir, data_type)
    return error

def check_recombine(obsID, directory=None, required_size=327680000, \
                        required_size_ics=30720000, startsec=None, n_secs=None):
    '''
    Checks that the number of files in directory (/astro/mwaops/vcs/[obsID]/combined/) is ....
    as that found on the archive and also checks that all files have the same size (327680000 by default).
    '''
    if not directory:
        directory = "/astro/mwaops/vcs/{0}/combined/".format(obsID)
    base = "\n Checking file size and number of files for obsID {0} in {1} for ".format(obsID, directory)
    n_secs = n_secs if n_secs else 1
    print base + "gps times {0} to {1}".format(startsec, startsec+n_secs-1) if startsec else base + "the whole time range."
    required_size = required_size
    # we need to get the number of unique seconds from the file names
    files = np.array(getmeta(service='obs', params={'obs_id':obsID})['files'].keys())
    mask = np.array(['.dat' in file for file in files])
    if not startsec:
        times = [time[11:21] for time in files[mask]]
        n_secs = len(set(times))
        command = "ls -l %s/*ch*.dat | ((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | " %(directory) + \
            "awk '($5!=%s){print $9}' | tee >> %s/%s_all.txt | xargs rm -rf) 4>&1;" %(required_size, directory, obsID) + \
            "cat %s/%s_all.txt; rm -rf %s/%s_all.txt" %(directory, obsID, directory, obsID)
        output = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True).stdout
    else:
        output = subprocess.Popen(["count=0;for sec in `seq -w %s %s `;do let count=${count}+`ls -l %s/*${sec}*ch*.dat | " %(startsec, startsec+n_secs-1, directory) + \
                                       "((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | awk '($5!=%s) " %(required_size) + \
                                       "{print $9}' | tee >> %s/errors_%s.txt | xargs rm -rf) 4>&1`;done;" %(directory,startsec) +\
                                       "echo ${count}; cat %s/errors_%s.txt;rm -rf %s/errors_%s.txt" %(directory,startsec,directory,startsec)],
                                  stdout=subprocess.PIPE, shell=True).stdout

    output = output.readlines()
    files_in_dir = int(output[0].strip())

    expected_files = n_secs * 25
    error = False
    error, n_ics = check_recombine_ics(directory=directory, \
                                           startsec=startsec, n_secs=n_secs, required_size=required_size_ics)
    files_in_dir += n_ics
    if not files_in_dir == expected_files:
        print "We have {0} files but expected {1}".format(files_in_dir, expected_files)
        error = True
    for line in output[1:]:
        if 'dat' in line:
            print "Deleted {0} due to wrong size.".format(line.strip())
            error = True
    if not error:
        print "We have all {0} files as expected.".format(files_in_dir)
    return error

def check_recombine_ics(directory=None, startsec=None, n_secs=None, required_size=None, obsID=None):
    if not required_size:
        try:
            files, suffix, required_size = get_files_and_sizes(obsID, 'ics')
        except:
            traceback.print_exc()
            return True, 0

    if not startsec:
        output = subprocess.Popen(["ls -ltr %s/*ics.dat | awk '($5!=%s){print \"file \" $9 \" has size \" $5 \" (expected %s)\"}'" %(directory, required_size, required_size)],
                                  stdout=subprocess.PIPE, shell=True).communicate()[0]
        command = "ls -l %s/*ics.dat | ((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | " %(directory) + \
            "awk '($5!=%s){print $9}' | tee >> %s/ics_all.txt | xargs rm -rf) 4>&1;" %(required_size, directory) + \
            "cat %s/ics_all.txt; rm -rf %s/ics_all.txt" %(directory, directory)
        output = subprocess.Popen([command], stdout=subprocess.PIPE, shell=True).stdout
    else:
        n_secs = n_secs if n_secs else 1
        output = subprocess.Popen(["count=0;for sec in `seq -w %s %s `;do let count=${count}+`ls -l %s/*${sec}*ics.dat | " %(startsec, startsec+n_secs-1, directory) + \
                                       "((tee /dev/fd/5 | wc -l >/dev/fd/4) 5>&1 | awk '($5!=%s) " %(required_size) + \
                                       "{print $9}' | tee >> %s/errors_%s.txt | xargs rm -rf) 4>&1`;done;" %(directory,startsec) +\
                                       "echo ${count}; cat %s/errors_%s.txt;rm -rf %s/errors_%s.txt" %(directory,startsec,directory,startsec)],
                                  stdout=subprocess.PIPE, shell=True).stdout

    output = output.readlines()
    files_in_dir = int(output[0].strip())
    error = False
    if not files_in_dir == n_secs:
        print "We have {0} ics-files but expected {1}".format(files_in_dir, n_secs)
        error = True
    for line in output[1:]:
        if 'dat' in line:
            error = True
            line = line.strip()
            print "Deleted {0} due to wrong size.".format(line)
            dat_files = line.replace('_ics.dat','*.dat')
            rm_cmd = "rm -rf {0}".format(dat_files)
            print "Also running {0} to make sure ics files are rebuilt.".format(rm_cmd)
            rm = subprocess.Popen(rm_cmd, stdout=subprocess.PIPE, shell=True)
    if error == False:
        print "We have all {0} ICS files as expected.".format(files_in_dir)
    return error, files_in_dir

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

def get_files_and_sizes(obsID, mode):
    if mode == 'raw':
        suffix = '.dat'
    elif mode == 'tar_ics':
        suffix = '.tar'
    elif mode == 'ics':
        suffix = '_ics.dat'
    else:
        print "Wrong mode supplied. Options are raw, tar_ics, and ics"
        return
    print "Retrieving file info from MWA database for all {0} files...".format(suffix)
    meta = getmeta(service='obs', params={'obs_id':obsID})
    files = np.array(meta['files'].keys())
    mask = np.array([suffix in file for file in files])
    files = files[mask]
    sizes=np.array([meta['files'][f]['size'] for f in files])
    print "...Done. Expect all on database to be {0} bytes in size...".format(sizes[0])
    if np.all(sizes == sizes[0]):
        print "...yep they are. Now checking on disk."
        return list(files), suffix, sizes[0]
    else:
        print "Not all files have the same size. Check your data!"
        print "{0}".format(np.vstack((files,sizes)).T)
        return

def opt_parser():
    parser = argparse.ArgumentParser(description="scripts to check sanity of downloads and recombine.")
    parser.add_argument("-m", "--mode", type=str, choices=['download','recombine'],\
                          help="Mode you want to run: download, recombine", dest='mode', default=None)
    parser.add_argument("-d", "--data_type", type=str, choices=['11','15','16', 'raw','ics','tar_ics'],\
                          help="Only necessary when checking downloads. Types refer to those as definded " + \
                            "in voltdownload.py: 11 = Raw, 15 = ICS only, 16 = ICS and tarballs of recombined data.", \
                            dest='data_type', default=None)
    parser.add_argument("-o", "--obs", metavar="OBS ID", type=int, dest='obsID',\
                            help="Observation ID you want to process [no default]", default=None)
    parser.add_argument("-b", "--begin", metavar="start", type=int, dest='begin',\
                            help="gps time of first file to ckeck on [default=%(default)s]",\
                            default=None)
    parser.add_argument("-e", "--end", metavar="stop", type=int, dest='end',\
                            help="gps time of last file to ckeck on [default=%(default)s]",\
                            default=None)
    parser.add_argument("-a", "--all", action="store_true", default=False, help="Perform on entire observation span. Use instead of -b & -e. [default=%(default)s]")
    parser.add_argument("-i", "--increment", metavar="time increment", type=int, \
                            dest='increment',\
                            help="Effectively the number of seconds to ckeck for " +\
                            "starting at start time [default=%(default)s]",\
                            default=None)
    parser.add_argument("-s", "--size", type=int, dest='size',\
                          help="The files size in bytes that you expect all files" +\
                          " to have. Per default will figure this out from files on he archive" +\
                            "We expect 253440000 (download raw), 327680000" +\
                          " (recombined, not ics), 7865368576 (tarballs)", default=None)
    parser.add_argument("-S", "--size_ics", type=int, help='Size in bytes that' +\
                            "you expect the ics files to have. Default = %(default)s", \
                            dest='size_ics', default=30720000)
    parser.add_argument('-w', '--work_dir', type=str, dest='work_dir',\
                            help="Directory " + \
                            "to check the files in. Default is /astro/mwaops/vcs/" + \
                            "[obsID]/[raw,combined]")
    parser.add_argument("-V", "--version", action="store_true", help="Print version and quit")
    return parser.parse_args()

if __name__ == '__main__':
    args = opt_parser()
    work_dir_base = '/astro/mwaops/vcs/' + str(args.obsID)

    if args.version:
        try:
            import version
            print(version.__version__)
            sys.exit(0)
        except ImportError as ie:
            print("Couldn't import version.py - have you installed vcstools?")
            print("ImportError: {0}".format(ie))
            sys.exit(0)

    if (args.mode is None) or (args.obsID is None):
        print "ERROR: You must specify BOTH a mode and observation ID"
        sys.exit(1)

    if args.all:
        from mwa_metadb_utils import obs_max_min
        args.begin, args.end = obs_max_min(args.obsID)
    if args.end:
        if not args.begin:
            print "If you supply and end time you also *have* to supply a begin time."
            sys.exit(1)
        args.increment = args.end - args.begin + 1
        print "Checking {0} seconds.".format(args.increment)
    if not args.all and not args.begin:
        print "You have to either set the -a flag to process the whole obs or povide a start and stop time with -b and -e"
        sys.exit(1)
    if args.begin:
        if not args.end and not args.increment:
            print "If you specify a begin time you also have to provide either an end time (-e end) or the number of seconds to check via the increment flag (-i increment)"
            sys.exit(1)
    if args.mode == 'download':
        if not args.data_type:
            print "In download mode you need to specify the data type you downloaded."
            sys.exit(1)
        if args.data_type == '11':
            data_type = 'raw'
        elif args.data_type == '15':
            data_type = 'ics'
        elif args.data_type == '16':
            data_type = 'tar_ics'
        else:
            data_type = args.data_type
        if data_type == 'raw':
            work_dir = work_dir_base + '/raw/'
        else:
            work_dir = work_dir_base + '/combined/'
        if args.work_dir:
            work_dir = args.work_dir
        if data_type == 'raw' or data_type == 'tar_ics' or data_type == 'ics':
            sys.exit(check_download(args.obsID, directory=work_dir,
                                    startsec=args.begin, n_secs=args.increment, data_type=data_type))
    elif args.mode == 'recombine':
        required_size = 327680000
        if args.size:
            required_size = args.size
        required_size_ics = args.size_ics
        work_dir = work_dir_base + '/combined/'
        if args.work_dir:
            work_dir = args.work_dir
        sys.exit(check_recombine(args.obsID, directory=work_dir, required_size=required_size, \
                            required_size_ics=required_size_ics, startsec=args.begin, n_secs=args.increment))
    else:
        print "No idea what you want to do. This mode is not supported. Ckeck the help."
        sys.exit(1)