#! /usr/bin/env python

"""
Author: Nicholas Swainston
Creation Date: /03/2016

Some of the orignal code was created by Bradley Meyers

This code is used to list the sources within the beam of observations IDs or using --obs_for_source list all the observations for each source. The sources can be input serval ways: using a list of pulsar names (--pulsar), using a complete catalogue file of pulsars (--dl_PSRCAT) or RRATs (--RRAT and --dl_RRAT), using a compatable catalogue (--in_cat with the help of --names and --coordstype) or using a RA and DEC coordinate (--coords). The observation IDs can be input (--obsid) or gathered from a directory (--FITS_dir). The default is to search all observation IDs from http://mwa-metadata01.pawsey.org.au/metadata/ that have voltages and list every known pulsar from PSRCAT in each observation ID.

Two most comon uses for this code is to search a single observation ID for pulsars like so:
> find_pulsar_in_obs.py -o 1099414416
which will output a text file called 1099414416_analytic_beam.txt
or to search all observation IDs for a single pulsar like so:
> find_pulsar_in_obs.py -p J0534+2200 --obs_for_source
which will output a text file called J0534+2200_analytic_beam.txt
"""

__author__ = 'Nicholas Swainston'
__date__ = '2016-03-21'

#TODO: (BWM) might be worth trying to only load the necessary parts of modules rather than loading an ENTIRE module. The speed up will be minimal overall, but it's also just a bit neater.
# You can also just load module/part of modules internally within functions. So if a module is only used once, just load it in the local function rather than up here (globally).
import os
import sys
import math
import argparse
import urllib
import urllib2
import json
import subprocess
import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.table import Table
from astropy.time import Time
from mwapy.pb import primary_beam
import ephem
from mwapy import ephem_utils,metadata
import psycopg2
from contextlib import closing
from ConfigParser import SafeConfigParser
import mwa_metadb_utils as meta
import csv

def yes_no(answer):
    yes = set(['Y','yes','y', 'ye', ''])
    no = set(['N','no','n'])
     
    while True:
        choice = raw_input(answer).lower()
        if choice in yes:
           return True
        elif choice in no:
           return False
        else:
           print "Please respond with 'yes' or 'no'\n"


def sex2deg( ra, dec):
    """
    Convert sexagesimal coordinates to degrees.

    sex2deg( ra, dec)
    Args:
        ra: the right ascension in HH:MM:SS
        dec: the declination in DD:MM:SS
    """
    c = SkyCoord( ra, dec, frame='icrs', unit=(u.hourangle,u.deg))

    # return RA and DEC in degrees in degrees
    return [c.ra.deg, c.dec.deg]


def deg2sex( ra, dec):
    """
    Convert decimal coordingates into sexagesimal strings, i.e. hh:mm:ss.ss and dd:mm:ss.ss

    deg2sex( ra, dec)
    Args:
        ra: the right ascension in degrees
        dec: the declination in degrees
    """

    c = SkyCoord( ra, dec, frame='icrs', unit=(u.deg,u.deg))
    coords = c.to_string('hmsdms')
    coords = coords.replace('h',':').replace('d',':').replace('m',':').replace('s','')

    # return RA and DEC in "hh:mm:ss.ssss dd:mm:ss.ssss" form
    return coords


def get_psrcat_ra_dec(pulsar_list = None):
    """
    Uses PSRCAT to return a list of pulsar names, ras and decs. Not corrected for proper motion.
    Removes pulsars without any RA or DEC recorded
    If no pulsar_list given then returns all pulsar on the catalogue

    get_psrcat_ra_dec(pulsar_list = None)
    Args:
        pulsar_list: A space list of pulsar names eg: [J0534+2200, J0538+2817].
               (default: uses all pulsars)
    return [[Jname, RAJ, DecJ]]
    """
    params = ['Jname', 'Raj', 'Decj']
    
    for p in params:
        #Gets the output of PSRCAT for each pparameter for each pulsar as a list
        cmd = ['psrcat', '-c', p]
        #If input pulsar list add them all to the psrcat command
        if pulsar_list != None:
            for input_pulsar in pulsar_list:
                cmd.append(input_pulsar)
        output = subprocess.Popen(cmd,stdout=subprocess.PIPE).communicate()[0]
        if output.startswith("WARNING: PSR"):
            print "Pulsar not on psrcat."
            quit()
        temp = []
        
        #process output to extract parameters
        pulsars = output.split('\n')
        for pulsar in pulsars[4:-1]:
            data = pulsar.split()
            #skip empty rows
            if len(data) > 1:
                temp.append([data[1]])
        if p == params[0]:
            pulsar_ra_dec=temp
        else:
            pulsar_ra_dec = [pulsar_ra_dec[x] + temp[x] for x in range(len(pulsar_ra_dec))]
    return pulsar_ra_dec


def grab_source_alog(source_type = 'Pulsar', pulsar_list = None):
    """
    Creates a csv file of source names, RAs and Decs using web catalogues for ['Pulsar', 'FRB', 'GC', 'RRATs'].
    """
    modes = ['Pulsar', 'FRB', 'GC', 'RRATs']
    if source_type not in modes:
        print "Input source type not in known catalogues types. Please choose from: {0}".format(modes)

    #Download the catalogue from the respective website
    if source_type == 'FRB':
        website = ' http://www.frbcat.org/frbcat.csv'
        web_table = 'frbcat.csv'
    elif source_type == 'GC':
        website = 'http://physwww.physics.mcmaster.ca/~harris/mwgc.dat'
        web_table = 'mwgc.dat'
    elif source_type == 'RRATs':
        website = 'http://astro.phys.wvu.edu/rratalog/rratalog.txt'
        web_table = 'rratalog.txt'
    if source_type !='Pulsar':
        print "Downloading {0} catalogue from {1}".format(source_type, website)
        os.system('wget {0}'.format(website))

    #Get each source type into the format [[name, ra, dec]]
    name_ra_dec = []
    if source_type == 'Pulsar':
        name_ra_dec = get_psrcat_ra_dec(pulsar_list)
    elif source_type == 'FRB':
        #TODO it's changed and currently not working atm
        with open(web_table,"rb") as in_txt:
            lines = in_txt.readlines()
            data = []
            for l in lines[7:]:
                ltemp = l.strip('<td>').split('</td>')
                print ltemp
                if len(ltemp) > 2:
                    ratemp = ltemp[7].lstrip('<td>')
                    dectemp = ltemp[8].lstrip('<td>')
                    name_ra_dec.append([ltemp[0].lstrip('<td>')[:9],ratemp,dectemp])
    elif source_type == 'GC':
        with open(web_table,"rb") as in_txt:
            lines = in_txt.readlines()
            lines = lines[71:]
            data = []
            for l in lines[1:]:
                ratemp = l[25:37].rstrip().replace(' ',':')
                dectemp = l[38:51].rstrip().replace(' ',':')
                temp = [l[1:10].rstrip(),ratemp,dectemp]
                
                name_ra_dec.append(temp)
                if l.startswith('______'):
                    name_ra_dec = name_ra_dec[:-2]
                    break
    elif source_type == 'RRATs':
        with open(web_table,"rb") as in_txt:
            lines = in_txt.readlines()
            data = []
            for l in lines[1:]:
                columns = l.strip().replace(" ", '\t').split('\t')
                temp = []
                if pulsar_list == None or (columns[0] in pulsar_list):
                    for entry in columns:
                        if entry not in ['', ' ', '\t']:
                            temp.append(entry.replace('--',''))
                    name_ra_dec.append([temp[0], temp[4], temp[5]])
    
    #remove web catalogue tables
    if source_type !='Pulsar':
        os.remove(web_table)

    return np.array(name_ra_dec)


def format_ra_dec(ra_dec_list, ra_col = 0, dec_col = 1):
    """
    Will format a list of lists containing RAs and Decs to uniform strings.  eg 00:00:00.00 -00:00:00.00. 
    An example input:
    format_ra_dec([[name,ra,dec]], ra_col = 1, dec_col = 2)
    """
    for i in range(len(ra_dec_list)):
        #make sure there are two digits in the HH slot for RA or DD for Dec
        if len(ra_dec_list[i][ra_col].split(':')[0]) == 1:
            ra_dec_list[i][ra_col] = '0' + ra_dec_list[i][ra_col]
        if ra_dec_list[i][dec_col][0].isdigit():
            if len(ra_dec_list[i][dec_col].split(':')[0]) == 1:
                ra_dec_list[i][dec_col] = '0' + ra_dec_list[i][dec_col]
        else:
            if len(ra_dec_list[i][dec_col].split(':')[0]) == 2:
                ra_dec_list[i][dec_col] = ra_dec_list[i][dec_col][0] + '0' +\
                                          ra_dec_list[i][dec_col][1:]

        #make sure there is a + on positive Decs
        if not ra_dec_list[i][dec_col].startswith('-') and\
           not ra_dec_list[i][dec_col].startswith('+'):
               ra_dec_list[i][dec_col] = '+' + ra_dec_list[i][dec_col]

        #since the ra a dec are the same except the +- in the dec just loop over it
        #and change the length
        ra_dec_col = [ra_col, dec_col]
        for n in range(2):
            if len(ra_dec_list[i][ra_dec_col[n]]) == int(2 + n):
                ra_dec_list[i][ra_dec_col[n]] += ':00:00.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 3 + n:
                ra_dec_list[i][ra_dec_col[n]] += '00:00.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 4 + n:
                ra_dec_list[i][ra_dec_col[n]] += '0:00.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 5 + n:
                ra_dec_list[i][ra_dec_col[n]] += ':00.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 6 + n:
                ra_dec_list[i][ra_dec_col[n]] += '00.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 7 + n:
                ra_dec_list[i][ra_dec_col[n]] += '0.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 8 + n:
                ra_dec_list[i][ra_dec_col[n]] += '.00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 9 + n:
                ra_dec_list[i][ra_dec_col[n]] += '00'
            elif len(ra_dec_list[i][ra_dec_col[n]]) == 10 + n:
                ra_dec_list[i][ra_dec_col[n]] += '0'

    return ra_dec_list


def calcFWHM(freq):
    """
    Calculate the FWHM for the beam assuming ideal response/gaussian-like profile. Will eventually be depricated.

    calcFWHM(freq)
    Args:
        freq: observation frequency in MHz
    """
    c = 299792458.0                 # speed of light (m/s)
    Dtile = 4.0                     # tile size (m) - incoherent beam
    freq = freq * 1e6               # convert from MHz to Hz
    fwhm = 1.2 * c / (Dtile * freq) # calculate FWHM using standard formula

    return fwhm


def singles_source_search(ra, dec):
    """
    Used to creates a 30 degree box around the source to make searching for obs_ids more efficient

    singles_source_search(ra, dec)
    Args:
        ra: ra of source in degrees
        dec: dec of source in degrees
    """
    ra = float(ra)
    dec = float(dec)
    box_size = 30.
    m_o_p = False # moved over (north or south) pole

    dec_top = dec + box_size
    if dec_top > 90.:
        dec_top = 90.
        m_o_p = True

    dec_bot = dec - box_size
    if dec_top < -90.:
        dec_top = -90.
        m_o_p = True

    if m_o_p:
        OBSID = []
        temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                    'minra':0., 'maxra':360.,
                                                    'mindec':dec_bot,'maxdec':dec_top})
        for row in temp:
            OBSID.append(row[0])
    else:
        ra_low = ra - 30. - box_size #30 is the how far an obs would drift in 2 hours(used as a max)
        ra_high = ra + box_size
        if ra_low < 0.:
            ra_new = 360 + ra_low
            OBSID = []
            temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                        'minra':ra_new, 'maxra':360.,
                                                        'mindec':dec_bot,'maxdec':dec_top})
            for row in temp:
                OBSID.append(row[0])
            temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                        'minra':0.,'maxra':ra_high,
                                                        'mindec':dec_bot,'maxdec':dec_top})
            for row in temp:
                OBSID.append(row[0])
        elif ra_high > 360:
            ra_new = ra_high - 360
            OBSID = []
            temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                        'minra':ra_low, 'maxra':360.,
                                                        'mindec':dec_bot,'maxdec':dec_top})
            for row in temp:
                OBSID.append(row[0])
            temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                        'minra':0., 'maxra':ra_new,
                                                        'mindec':dec_bot,'maxdec':dec_top})
            for row in temp:
                OBSID.append(row[0])
        else:
            OBSID =[]
            temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000,
                                                        'minra':ra_low, 'maxra':ra_high,
                                                        'mindec':dec_bot,'maxdec':dec_top})
            for row in temp:
                OBSID.append(row[0])
    return OBSID


def beam_enter_exit(powers, dt, duration, min_power = 0.3):
    """
    Calculates when the source enters and exits the beam

    beam_enter_exit(min_power, powers, imax, dt):
        powers: list of powers fo the duration every dt and freq powers[times][freqs]
        dt: the time interval of how often powers are calculated
        duration: duration of the observation according to the metadata in seconds
        min_power: zenith normalised power cut off 
    """
    from scipy.interpolate import UnivariateSpline
    time_steps = range(0, duration, dt) 

    #For each time step record the min power so even if the source is in 
    #one freq channel it's recorded
    powers_freq_min = []
    for p in powers:
        powers_freq_min.append(float(min(p) - min_power))

    if min(powers_freq_min) > 0.:
        enter = 0.
        exit = 1.
    else:
        spline = UnivariateSpline(time_steps, powers_freq_min , s=0)
        if len(spline.roots()) == 2: 
            enter, exit = spline.roots()
            enter /= duration
            exit /= duration
        elif len(spline.roots()) == 1:
            if powers_freq_min[0] > powers_freq_min[-1]:
                #power declines so starts in beem then exits
                enter = 0.
                exit = spline.roots()/duration
            else:
                enter = spline.roots()/duration
                exit = 0.
        else:
            enter = 0.
            exit = 1.
    return enter, exit


def cal_on_database_check(obsid):
    from mwa_pulsar_client import client
    web_address = 'mwa-pawsey-volt01.pawsey.ivec.org'
    auth = ('mwapulsar','veovys9OUTY=')
    detection_list = client.detection_list(web_address, auth)
    
    cal_used = False
    cal_avail = False
    for d in detection_list:
        if int(d[u'observationid']) == int(obsid):
            if d[u'calibrator'] is not None:
                cal_used = True
                #TODO add a check if there is a cal file option
    
    #No cal
    check_result = 'N'
    if cal_avail:
        #Cal available
        check_result = 'A'
    elif cal_used:
        #Cal used
        check_result = 'U'
    
    return check_result


def get_beam_power_over_time(beam_meta_data, names_ra_dec,
                             dt=296, centeronly=True, verbose=False, 
                             option = 'a'):
    """
    Calulates the power (gain at coordinate/gain at zenith) for each source over time.

    get_beam_power_over_time(beam_meta_data, names_ra_dec,
                             dt=dt, centeronly=True, verbose=False,          
                             option = 'a', output = './')
    Args:
        beam_meta_data: [obsid,ra, dec, time, delays,centrefreq, channels] 
                        obsid metadata obtained from meta.get_common_obs_metadata
        names_ra_dec: and array in the format [[source_name, RAJ, DecJ]]
        dt: time step in seconds for power calculations (default 296)
        centeronly: only calculates for the centre frequency (default True)
        verbose: prints extra data to (default False)
        option: primary beam model ['a','d','e']: analytical, advanced, full_EE
    """
    obsid,ra, dec, time, delays,centrefreq, channels = beam_meta_data
    print "Calculating beam power for OBS ID: {0}".format(obsid)

    starttimes=np.arange(0,time,dt)
    stoptimes=starttimes+dt
    stoptimes[stoptimes>time]=time
    Ntimes=len(starttimes)
    midtimes=float(obsid)+0.5*(starttimes+stoptimes)

    mwa = ephem_utils.Obs[ephem_utils.obscode['MWA']]
    # determine the LST
    observer = ephem.Observer()
    # make sure no refraction is included
    observer.pressure = 0
    observer.long = mwa.long / ephem_utils.DEG_IN_RADIAN
    observer.lat = mwa.lat / ephem_utils.DEG_IN_RADIAN
    observer.elevation = mwa.elev

    if not centeronly:
        PowersX=np.zeros((len(names_ra_dec),
                             Ntimes,
                             len(channels)))
        PowersY=np.zeros((len(names_ra_dec),
                             Ntimes,
                             len(channels)))
        # in Hz
        frequencies=np.array(channels)*1.28e6
    else:
        PowersX=np.zeros((len(names_ra_dec),
                             Ntimes,1))
        PowersY=np.zeros((len(names_ra_dec),
                             Ntimes,1))
        frequencies=[centrefreq]
    
    RAs, Decs = sex2deg(names_ra_dec[:,1],names_ra_dec[:,2])
    if len(RAs)==0:
        sys.stderr.write('Must supply >=1 source positions\n')
        return None
    if not len(RAs)==len(Decs):
        sys.stderr.write('Must supply equal numbers of RAs and Decs\n')
        return None
    for itime in xrange(Ntimes):
        obstime = Time(midtimes[itime],format='gps',scale='utc')
        observer.date = obstime.datetime.strftime('%Y/%m/%d %H:%M:%S')
        LST_hours = observer.sidereal_time() * ephem_utils.HRS_IN_RADIAN

        HAs = -RAs + LST_hours * 15
        Azs, Alts = ephem_utils.eq2horz(HAs, Decs, mwa.lat)
        # go from altitude to zenith angle
        theta=np.radians(90.-Alts)
        phi=np.radians(Azs)

        #Decide on beam model
        if option == 'a':
            for ifreq in xrange(len(frequencies)):
                rX,rY=primary_beam.MWA_Tile_analytic(theta, phi,
                                                     freq=frequencies[ifreq], delays=delays,
                                                     zenithnorm=True,
                                                     power=True)
                PowersX[:,itime,ifreq]=rX
                PowersY[:,itime,ifreq]=rY
        elif option == 'd':
            for ifreq in xrange(len(frequencies)):
                rX,rY=primary_beam.MWA_Tile_advanced(theta, phi,
                                                     freq=frequencies[ifreq], delays=delays,
                                                     zenithnorm=True,
                                                     power=True)
                PowersX[:,itime,ifreq]=rX
                PowersY[:,itime,ifreq]=rY
        elif option == 'e':
            for ifreq in xrange(len(frequencies)):
                rX,rY=primary_beam.MWA_Tile_full_EE(theta, phi,
                                                     freq=frequencies[ifreq], delays=delays,
                                                     zenithnorm=True,
                                                     power=True)
                PowersX[:,itime,ifreq]=rX
                PowersY[:,itime,ifreq]=rY
            #print '{0:.2f}'.format(100.*float(itime)/float(Ntimes))+"% complete for obsid: "+str(obsid)
    Powers=0.5*(PowersX+PowersY)
    return Powers



def get_beam_power(obsid_data,
                   sources, 
                   coord1 = 'Raj',
                   coord2 = 'Decj',
                   names = 'Jname',
                   dt=296,
                   centeronly=True,
                   verbose=False,
                   min_power=0.3,
                   option = 'a',
                   output = "./",
                   cal_check = False):
      
    outputfile = output
    primary_beam_output_file = outputfile + str(obsid) + '_' + beam_string + '_beam.txt'
    if os.path.exists(primary_beam_output_file):
        os.remove(primary_beam_output_file)
    with open(primary_beam_output_file,"wb") as out_list:
        out_list.write('All of the sources that the ' + beam_string + ' beam model calculated a power of '\
                       + str(min_power) + ' or greater for observation ID: ' + str(obsid) + '\n' +\
                       'Observation data :RA(deg): ' + str(ra) + ' DEC(deg): ' + str(dec)+' Duration(s): ' \
                       + str(time) + '\n')
        if cal_check:
            #checks the MWA Pulsar Database to see if the obsid has been 
            #used or has been calibrated
            print "Checking the MWA Pulsar Databse for the obsid: {0}".format(obsid)
            cal_check_result = cal_on_database_check(obsid)
            out_list.write("Calibrator Availability: {0}\n".format(cal_check_result))
        out_list.write('Source  Time of max power in observation    File number source entered the '\
                       + 'beam    File number source exited the beam       Max Power \n')
        counter=0
        for sourc in Powers:
            counter = counter + 1
            if max(sourc) > min_power:
                for imax in range(len(sourc)):
                    if sourc[imax] == max(sourc):
                        max_time = midtimes[imax]
                        enter, exit = beam_enter_exit(min_power, sourc, imax, dt, time)
                        out_list.write(str(sources[names][counter - 1])  + ' ' + \
                                str(int(max_time) - int(obsid)) + ' ' + str(enter) + ' ' + str(exit) +\
                                ' ' + str(max(sourc)[0]) + "\n")
        print "A list of sources for the observation ID: " + str(obsid) + \
              " has been output to the text file: " + str(obsid) + '_' + beam_string + '_beam.txt'
    return enter, exit


def get_beam_power_obsforsource(obsid_data,
                   sources,
                   coord1 = 'Raj',
                   coord2 = 'Decj'):
    counter = 0
    for sourc in temp_power:
            counter = counter + 1
            if max(sourc) > min_power:
                print obsid

                for imax in range(len(sourc)):
                    if sourc[imax] == max(sourc):
                        max_time = float(midtimes[imax]) - float(obsid)
                        Powers.append([sources[names][counter-1], obsid, time, max_time, sourc, imax, max(sourc)])

    for sourc in sources:
        outputfile = output
        primary_beam_output_file = outputfile + str(sourc[names]) + beam_string + '_beam.txt'
        if os.path.exists(primary_beam_output_file):
            os.remove(primary_beam_output_file)
        with open(outputfile + str(sourc[names]) + beam_string + '_beam.txt',"wb") as out_list:
            out_list.write('All of the observation IDs that the ' + beam_string + ' beam model calculated a power of '\
                           + str(min_power) + ' or greater for the source: ' + str(sourc[names]) + '\n' +\
                           'Obs ID   Duration  Time during observation that the power was at a'+\
                           ' maximum    File number source entered    File number source exited  Max power')
            if cal_check:
                out_list.write("   Cal\n")
            else:
                out_list.write("\n")
                
            for p in Powers:
                if str(p[0]) == str(sourc[names]):
                    enter, exit = beam_enter_exit(min_power, p[4], p[5], dt, time)
                    out_list.write(str(p[1]) + ' ' + str(p[2]) + ' ' + str(p[3]) + ' ' + str(enter) +\
                                   ' ' + str(exit) + ' ' + str(p[6][0]))
                    if cal_check:
                        #checks the MWA Pulsar Database to see if the obsid has been 
                        #used or has been calibrated
                        print "Checking the MWA Pulsar Databse for the obsid: {0}".format(p[1])
                        cal_check_result = cal_on_database_check(p[1])
                        out_list.write(" {0}\n".format(cal_check_result))
                    else:
                        out_list.write("\n")


    print "A list of observation IDs that containt: " + str(sourc[names]) + \
              " has been output to the text file: " + str(sourc[names]) + beam_string + '_beam.txt'
    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description="""
    This code is used to list the sources within the beam of observations IDs or using --obs_for_source list all the observations for each source. The sources can be input serval ways: using a list of pulsar names (--pulsar), using a complete catalogue file of pulsars (--dl_PSRCAT) or RRATs (--RRAT and --dl_RRAT), using a compatable catalogue (--in_cat with the help of --names and --coordstype) or using a RA and DEC coordinate (--coords). The observation IDs can be input (--obsid) or gathered from a directory (--FITS_dir). The default is to search all observation IDs from http://mwa-metadata01.pawsey.org.au/metadata/ that have voltages and list every known pulsar from PSRCAT in each observation ID.
    """)
    parser.add_argument('--obs_for_source',action='store_true',help='Instead of listing all the sources in each observation it will list all of the observations for each source. For increased efficiency it will only search OBSIDs within the primary beam.')
    parser.add_argument('--output',type=str,help='Chooses a file for all the text files to be output to. The default is your current directory', default = './')
    parser.add_argument('-b','--beam',type=str,help='Decides the beam approximation that will be used. Options: "a" the analytic beam model (2012 model, fast and reasonably accurate), "d" the advanced beam model (2014 model, fast and slighty more accurate) or "e" the full EE model (2016 model, slow but accurate). " Default: "a"',default = "a")
    parser.add_argument('-m','--min_power',type=float,help='The minimum fraction of the zenith normalised power that a source needs to have to be recorded. Default 0.3', default=0.3)
    parser.add_argument("-V", "--version", action="store_true", help="Print version and quit")
    #impliment an option for the accurate beam later on and maybe the old elipse approximation if I can make it accurate

    #source options
    sourargs = parser.add_argument_group('Source options', 'The different options to control which sources are used. Default is all known pulsars.')
    sourargs.add_argument('-p','--pulsar',type=str, nargs='*',help='Searches for all known pulsars. This is the default. To search for individual pulsars list their Jnames in the format " -p J0534+2200 J0630-2834"', default = None)
    sourargs.add_argument('--source_type',type=str, default = 'Pulsar', help="An astronomical source type from ['Pulsar', 'FRB', 'GC', 'RRATs'] to search for all sources in their respective web catalogue.")
    sourargs.add_argument('--in_cat',type=str,help='Location of source catalogue, must be a csv where each line is in the format "source_name, hh:mm:ss.ss, +dd:mm:ss.ss".')
    sourargs.add_argument('-c','--coords',type=str,nargs='*',help='String containing coordinates in "RA,DEC". This will list the OBS IDs that contain this coordinate. Must be enterered as: "hh:mm:ss.ss,+dd:mm:ss.ss".')
    #finish above later and make it more robust to incclude input as sex or deg and perhaps other coordinte systmes

    #observation options
    obargs = parser.add_argument_group('Observation ID options', 'The different options to control which observation IDs are used. Default is all observation IDs with voltages.')
    obargs.add_argument('--FITS_dir',type=str,help='Instead of searching all OBS IDs, only searchs for the obsids in the given directory. Does not check if the .fits files are within the directory. Default = /group/mwaops/vcs')
    obargs.add_argument('-o','--obsid',type=str,nargs='*',help='Input several OBS IDs in the format " -o 1099414416 1095506112". If this option is not input all OBS IDs that have voltages will be used')
    obargs.add_argument('--all_volt',action='store_true',help='Includes observation IDs even if there are no raw voltages in the archive. Some incoherent observation ID files may be archived even though there are raw voltage files. The default is to only include files with raw voltage files.')
    obargs.add_argument('--cal_check',action='store_true',help='Check the MWA Pulsar Database to check if the obsid has every succesfully detected a pulsar and if it has a calibration solution.')
    args=parser.parse_args()

    if args.version:
        try:
            import version
            print(version.__version__)
            sys.exit(0)
        except ImportError as ie:
            print("Couldn't import version.py - have you installed vcstools?")
            print("ImportError: {0}".format(ie))
            sys.exit(0)

    #Parse source options
    if args.in_cat and args.coords:
        print "Can't use --in_cat and --coords. Please input your cooridantes using one method"
    print "Gathering sources"
    if args.in_cat:
        names_ra_dec = []
        with open(args.in_cat,"r") as input_catalogue:
            reader = csv.reader(input_catalogue)
            for row in reader:
                names_ra_dec.append(row)
    elif args.coords:
        names_ra_dec = []
        for cn, c in enumerate(args.coords):
            names_ra_dec.append(['source_{0}'.format(cn+1),c.split(',')[0],c.split(',')[1]])
    else:
        names_ra_dec = grab_source_alog(source_type = args.source_type, pulsar_list = args.pulsar)
    
    #format ra and dec
    names_ra_dec = format_ra_dec(names_ra_dec, ra_col = 1, dec_col = 2)
    names_ra_dec = np.array(names_ra_dec)
    
    #Check if the user wants to use --obs for source
    if (len(names_ra_dec) ==1) and (not args.obs_for_source):
        args.obs_for_source = yes_no('You are only searching for one pulsar so it is '+\
                                     'recommened that you use --obs_for_source. Would '+\
                                     'you like to use --obs_for_source. (Y/n)')
        if args.obs_for_source:
            print "Using option --obs_for_source"
        else:
            print "Not using option --obs_for_source"
    
   
    #get obs IDs
    if args.obsid and args.FITS_dir:
        print "Can't use --obsid and --FITS_dir at the same time. Exiting"
        quit()
    print "Gathering observation IDs"
    if args.obsid:
        obsid_list = args.obsid
    elif args.FITS_dir:
        obsid_list = os.walk(args.FITS_dir).next()[1]
    elif len(names_ra_dec) ==1:
        #if there is a single pulsar simply use nearby obsids
        ob_ra, ob_dec = sex2deg(names_ra_dec[0][1],names_ra_dec[0][2])
        obsid_list = singles_source_search(ob_ra, ob_dec)
    else:
        #use all obsids
        temp = meta.getmeta(service='find', params={'mode':'VOLTAGE_START','limit':10000})
        obsid_list = []
        for row in temp:
            obsid_list.append(row[0])
    
    
    if args.beam == 'e':
        dt = 300
    else:
        dt = 100
    
    #prepares metadata calls and calculates power
    powers = []
    #powers[obsid][source][time][freq]
    obsid_meta = []
    for obsid in obsid_list:
        beam_meta_data, full_meta = meta.get_common_obs_metadata(obsid, return_all = True)
        #beam_meta_data = obsid,ra_obs,dec_obs,time_obs,delays,centrefreq,channels

        #check for raw volatge files
        filedata = full_meta[u'files']
        keys = filedata.keys()
        check = False
        for k in keys:
            if '.dat' in k: #TODO check if is still robust
                check = True
        if check or args.all_volt:
            powers.append(get_beam_power_over_time(beam_meta_data, names_ra_dec,
                                    dt=dt, centeronly=True, verbose=False, 
                                    option = args.beam))
            obsid_meta.append(beam_meta_data)
        else:
            print('No raw voltage files for %s' % obsid)
            obsid_list.remove(obsid)

    print "power len: " + str(len(powers))
    print "obs len: " + str(len(obsid_list))
    print powers

    #chooses whether to list the source in each obs or the obs for each source
    if args.obs_for_source:
        for sn, source in enumerate(names_ra_dec):
            out_name = "{0}_{1}_beam.txt".format(source[0],args.beam)
            with open(out_name,"wb") as output_file:
                output_file.write('#All of the observation IDs that the {0} beam model calculated a power of {1} or greater for the source: {2}\n'.format(args.beam,args.min_power, source[0])) 
                output_file.write('#Obs ID,   Duration,   Obs fraction source entered,    Obs fractiong source exited,  Max power')
                if args.cal_check:
                    output_file.write("   Cal\n")
                else:
                    output_file.write('\n')

                for on, obsid in enumerate(obsid_list):
                    source_ob_power = powers[on][sn]
                    if max(source_ob_power) > args.min_power:
                        print source_ob_power
                        duration = obsid_meta[on][3]
                        enter, exit = beam_enter_exit(source_ob_power, dt,
                                                      duration, min_power = args.min_power) 
                        output_file.write('{0} {1} {2} {3} {4}'.format(obsid,duration, enter, exit, max(source_ob_power)[0]))
                        if args.cal_check:
                            #checks the MWA Pulsar Database to see if the obsid has been 
                            #used or has been calibrated
                            print "Checking the MWA Pulsar Databse for the obsid: {0}".format(p[1])
                            cal_check_result = cal_on_database_check(p[1])
                            output_file.write(" {0}\n".format(cal_check_result))
                        else:
                            output_file.write("\n")
    else:
        #output a list of sorces foreach obs
        for on, obsid in enumerate(obsid_list):
            out_name = "{0}_{1}_beam.txt".format(obsid,args.beam)
            duration = obsid_meta[on][3]
            with open(out_name,"wb") as out_list:
                out_list.write('#All of the sources that the {0} beam model calculated a power of {1} or greater for observation ID: {2}\n'.format(args.beam, args.min_power,obsid))
                out_list.write('#Observation data :RA(deg): {0} DEC(deg): {1} Duration(s): {2}\n'.format(obsid_meta[on][1],obsid_meta[on][2],duration))
                if args.cal_check:
                    #checks the MWA Pulsar Database to see if the obsid has been 
                    #used or has been calibrated
                    print "Checking the MWA Pulsar Databse for the obsid: {0}".format(obsid)
                    cal_check_result = cal_on_database_check(obsid)
                    out_list.write("Calibrator Availability: {0}\n".format(cal_check_result))
                out_list.write('#Source,  Obs frac source entered the '\
                               + 'beam,    Obs frac source exited the beam,    Max Power \n')
                for sn, source in enumerate(names_ra_dec):
                    source_ob_power = powers[on][sn]
                    if max(source_ob_power) > args.min_power:
                        enter, exit = beam_enter_exit(source_ob_power, dt,
                                                      duration, min_power = args.min_power)
                        out_list.write('{0} {1} {2} {3} \n'.format(source[0],enter,exit,max(source_ob_power)[0]))


    print "The code is complete and all results have been output to text files"


