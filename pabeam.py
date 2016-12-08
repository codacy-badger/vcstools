#/usr/bin/env python


"""
Script to calcaulte the array factor and determine the tied-array beam of the MWA.

Author: Bradley Meyers
Date: 14 Nov 2016
"""




import numpy as np
from scipy.integrate import simps
from scipy.interpolate import interp2d
from astropy.coordinates import SkyCoord,EarthLocation,AltAz
from astropy.time import Time
from astropy.io import fits
import astropy.units as u
from astropy.constants import c,k_B
import matplotlib as mpl
#mpl.use('Qt4Agg')
mpl.rcParams['agg.path.chunksize'] = 10000
import matplotlib.pyplot as plt
#from mpl_toolkits.mplot3d import Axes3D
import sys
import os
from mpi4py import MPI
import argparse
#from multiprocessing import Pool,Queue,Process
from mwapy.pb import primary_beam as pb
import urllib
import urllib2
import json
from mwapy import ephem_utils,metadata
#import progressbar



def getmeta(service='obs', params=None):
    """
    getmeta(service='obs', params=None)
    
    Given a JSON web service ('obs', find, or 'con') and a set of parameters as
    a Python dictionary, return the RA and Dec in degrees from the Python dictionary.
    """
    BASEURL = 'http://mwa-metadata01.pawsey.org.au/metadata/'
    if params:
        data = urllib.urlencode(params)  # Turn the dictionary into a string with encoded 'name=value' pairs
    else:
        data = ''
    #Validate the service name
    if service.strip().lower() in ['obs', 'find', 'con']:
        service = service.strip().lower()
    else:
        print "invalid service name: %s" % service
        return
    #Get the data
    try:
        result = json.load(urllib2.urlopen(BASEURL + service + '?' + data))
    except urllib2.HTTPError as error:
        print "HTTP error from server: code=%d, response:\n %s" % (error.code, error.read())
        return
    except urllib2.URLError as error:
        print "URL or network error: %s" % error.reason
        return
    #Return the result dictionary
    return result


def get_delay_steps(obs):
    #for line in txtfile:
    beam_meta_data = getmeta(service='obs', params={'obs_id':obs})
    obn = beam_meta_data[u'obsname']
    ra = beam_meta_data[u'metadata'][u'ra_pointing']
    dec = beam_meta_data[u'metadata'][u'dec_pointing']
    dura = beam_meta_data[u'stoptime'] - beam_meta_data[u'starttime'] #gps time
    mode = beam_meta_data[u'mode']
    Tsky = beam_meta_data[u'metadata'][u'sky_temp']
    xdelays = beam_meta_data[u'rfstreams'][u"0"][u'xdelays']

    minfreq = float(min(beam_meta_data[u'rfstreams'][u"0"][u'frequencies']))
    maxfreq = float(max(beam_meta_data[u'rfstreams'][u"0"][u'frequencies']))
    channels = beam_meta_data[u'rfstreams'][u"0"][u'frequencies']
    centrefreq = 1.28 * (minfreq + (maxfreq-minfreq)/2)
    #print "{0}  {1:<15}  {2:3.2f}   {3:4.2f}    {4:>4}      {5}   {6}".format(ob,obn,ra,dec,dura,centrefreq,Tsky)
    #print xdelays

    return [obs,ra,dec,dura,xdelays,centrefreq,channels]



def getTileLocations(obsid,flags=[]):
	"""
	Function grab the MWA tile locations for any given observation ID. Downloads the relevant metafits file from the database, saves it as <obdID>_metafits_ppds.fits.
	
	Input:
	  obsid - the GPS observation ID
	  flags - RTS tile flags (i.e. the first entry in the metafits correspond to "tile 0", irrespective of what the antenna name is) 

	Return:
	  a list of lists containing the following:
		list[0] = a list of tile positions East of the array centre
		list[1] = a list of tile positions North of the array centre
		list[2] = a list of tile heights about sea-level 
	"""

	f = fits.open('{0}_metafits_ppds.fits'.format(obsid))		
	#names = f[1].data['Antenna'][::2]
	east = f[1].data['East'][::2]
	north = f[1].data['North'][::2]
	height = f[1].data['Height'][::2] # height above sea-level
	# MWA array centre height above sea-level
	mwacentre_h = 377.827
	height = height - mwacentre_h

	#flag the tile from flag
	for i in flags:
		east = np.delete(east,i)
		north = np.delete(north,i)
		height = np.delete(height,i)
			
	return east,north,height


def get_obstime_duration(obsid):
	"""
	Funciton to grab the recorded start-time and duration of the observation
	
	Input:
	  obsid - the GPS observation ID

	Return:
	  a list containing the folloing two items (in order):
		list[0] = observation starting time in UTC
		list[1] = observation duration in seconds
	"""
	# metafits file will already have been downloaded
	f = fits.open('{0}_metafits_ppds.fits'.format(obsid))
	
	return [f[0].header['DATE-OBS'],f[0].header['EXPOSURE']]


def getTargetAZZA(ra,dec,time,lat=-26.7033,lon=116.671,height=377.827):
	"""
	Function to get the target position in alt/az at a given EarthLocation and Time.
	
	Default lat,lon,height is the centre of  MWA.

	Input:
	  ra - target right ascension in astropy-readable format
	  dec - target declination in astropy-readable format
	  time - time of observation in UTC (i.e. a string on form: yyyy-mm-dd hh:mm:ss.ssss)
	  lat - observatory latitude in degrees
	  lon - observatory longitude in degrees

	Returns:
	  a list containing four elements in the following order:
		list[0] = target azimuth in radians
		list[1] = target zenith angle in radians
		list[2] = target azimuth in degrees
		list[3] = target zenith angle in degrees
	"""
	#print "Creating EarthLocation for: lat = {0} deg, lon = {1} deg".format(lat,lon)
	location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=height*u.m)
	
	#print "Creating SkyCoord for target at (RA,DEC) = ({0},{1})".format(ra,dec)
	coord = SkyCoord(ra,dec,unit=(u.hourangle,u.deg))
	#print "Target at: ({0},{1}) deg".format(coord.ra.deg,coord.dec.deg)
	
	obstime = Time(time)
	#print "Observation time: {0}".format(obstime.iso)
	
	#print "Converting to Alt,Az for given time and observatory location..."
	altaz = coord.transform_to(AltAz(obstime=obstime,location=location))
	#print "Target (Alt,Az) = ({0},{1}) deg".format(altaz.alt.deg,altaz.az.deg)
	
	#print "Converting to (Az,ZA)"
	az = altaz.az.rad 
	azdeg = altaz.az.deg
	 
	za = np.pi/2 - altaz.alt.rad
	zadeg = 90 - altaz.alt.deg
	
	#print "Target (Az,ZA) = ({0},{1}) deg".format(azdeg,zadeg)

	return [az,za,azdeg,zadeg]


def calcWaveNumbers(wl,p,t):
	"""
	Function to calculate the 3D wavenumbers for a given wavelength and az/za grid.

	Input:
	  wl - central wavelength for the observation
	  az - azimuth (either a scalar or an array)
	  za - zenith angle (either a scalar or an array)
	
	Return:
	  [kx,ky,kz] - the 3D wavenumbers 
	"""
	# the standard equations are:
	#	a = 2 * pi / lambda
	#	kx = a * sin(theta) * cos(phi)
	#	ky = a * sin(theta) * sin(phi)
	#	kz = a * cos(theta)
	# this is assuming that theta,phi are in the convention from Sutinjo et al. 2015
	#	i.e. phi = pi/2 - az
	kx = (2*np.pi/wl) * np.sin(t) * np.cos(p)
	ky = (2*np.pi/wl) * np.sin(t) * np.sin(p)
	kz = (2*np.pi/wl) * np.cos(t)

	return [kx,ky,kz]

# Make generator functions for Azimuth and Zenith so we don't have to create the whole
# meshgrid at once and then store it.
# This is far more memory efficient that storing the entire AZ and ZA planes in memory, 
# especially with the required resolution.
def genAZZA(start,stop,step,end=False):
	i = 0
	num = int((stop-start)/step)
	while i<num:
		yield start+i*step
		i += 1
	if end:
		yield stop
	return
    
def createArrayFactor(targetRA,targetDEC,obsid,delays,obstime,obsfreq,eff,flagged_tiles,theta_res,phi_res,coplanar,zenith,start,end):
	"""
	Main function that organises the information required and plots results/outputs info.
	"""	
	#print np.degrees(start),np.degrees(end)
        #def calcArrayFactor(az,za,xpos,ypos,zpos,obswl,targetAZ,targetZA):
        #    """
        #    Actually do the array factor calcualtion on a grid
        #    """
        #    fx = np.zeros_like(az,dtype=np.complex64)
        #    bar = progressbar.ProgressBar(widgets=[progressbar.Percentage(),progressbar.Bar(),progressbar.ETA()]).start()
        #    
        #    kx,ky,kz = calcWaveNumbers(obswl,np.pi/2-az,za)
        #    target_kx,target_ky,target_kz = calcWaveNumbers(obswl,np.pi/2-targetAZ,targetZA)
        #    
        #    for x,y,z in bar(zip(xpos,ypos,zpos)):
	#	#fx += calcAX([x,y,z,kx,ky,kz,target_kx,target_ky,target_kz])
        #        np.add(fx,calcAX([x,y,z,kx,ky,kz,target_kx,target_ky,target_kz]),out=fx)  
	#
        #    # Normalise: fx = fx/len(xpos)
        #    fx /= len(xpos)
        #    print "normalised maximum:",np.max(np.abs(fx)**2)
	#
        #    return fx
            
            
        #def plot_polar(az,za,tilebeam,af,tabeam,obsid,obsfreq,targetAZ,targetZA,suffix):
        #    fig = plt.figure()
        #    ax = fig.add_subplot(111,polar=True)
        #    cc=ax.contourf(az,za,tilebeam,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    ax.set_rlabel_position(-45)
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_gx_{1:.2f}MHz_{2:.2f}_{3:.2f}_polar_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))
        #    plt.clf()
	#
        #    fig = plt.figure()
        #    ax = fig.add_subplot(111,polar=True)
        #    cc=ax.contourf(az,za,np.abs(af)**2,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    ax.set_rlabel_position(-45)
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_fx_{1:.2f}MHz_{2:.2f}_{3:.2f}_polar_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))
        #    plt.clf()
	#
        #    fig = plt.figure()
        #    ax = fig.add_subplot(111,polar=True)
        #    cc=ax.contourf(az,za,tabeam,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    ax.set_rlabel_position(-45)
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_gxfx_{1:.2f}MHz_{2:.2f}_{3:.2f}_polar_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))	
        #    plt.clf()

        #def plot_cartesian(az,za,tilebeam,af,tabeam,obsid,obsfreq,targetAZ,targetZA,suffix):
        #    fig = plt.figure()
        #    ax = fig.add_subplot(111)
        #    cc=ax.contourf(az,za,tilebeam,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_gx_{1:.2f}MHz_{2:.2f}_{3:.2f}_cart_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))
        #    plt.clf()

        #   fig = plt.figure()
        #   ax = fig.add_subplot(111)
        #    cc=ax.contourf(az,za,np.abs(af)**2,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_fx_{1:.2f}MHz_{2:.2f}_{3:.2f}_cart_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))
        #    plt.clf()
	#
        #    fig = plt.figure()
        #    ax = fig.add_subplot(111)
        #    cc=ax.contourf(az,za,tabeam,50,cmap=plt.get_cmap('jet'))
        #    ax.set_xlabel("Azimuth [rad]")
        #    ax.set_ylabel("Zenith Angle [rad]")
        #    plt.colorbar(cc,label="normalised power")
        #    plt.savefig("{0}_gxfx_{1:.2f}MHz_{2:.2f}_{3:.2f}_cart_{4}.png".format(obsid,obsfreq/1e6,targetAZ,targetZA,suffix))	
        #    plt.clf()
        


	# convert frequency to wavelength
	obswl = obsfreq/c.value
	#print "Evaluating array factor at {0:.3f} MHz ({1:.3f} m)".format(obsfreq/1e6,obswl)
	
	# get the array tile positions
	#print "Getting tile locations"
	xpos,ypos,zpos = getTileLocations(obsid,flagged_tiles)
	#print "\t defined tile positions with:"
	#print "\t\t x = distance East from array centre, in metres"
	#print "\t\t y = distance North from array centre, in metres"
	#print "\t\t z = height above array centre, in metres"

	if coplanar: 
		#print "Assuming array is co-planar"
		zpos = np.zeros(len(zpos))

	#print "\tafter flagging, there are {0} tiles left to form a tied-array beam".format(len(xpos))

	# get observation information (start-time, duration, etc)
	#print "Retrieving observation start time and duration"
	t,d = get_obstime_duration(obsid) 
	if obstime is None:
		time = t.replace("T"," ")
	else:
		#print "Over-riding observation time with user-given option"
		time = obstime
	
	# get the target azimuth and zenith angle in radians and degrees
	# these are define in the normal sense: za = 90 - elevation, az = angle east of North (i.e. E=90)
	if zenith:
		#print "Assuming a zenith pointing"
		targetAZ,targetZA,targetAZdeg,targetZAdeg = 0,0,0,0
	else:
        	targetAZ,targetZA,targetAZdeg,targetZAdeg = getTargetAZZA(targetRA,targetDEC,time)

	target_kx,target_ky,target_kz = calcWaveNumbers(obswl,np.pi/2-targetAZ,targetZA)


	results = []
	lastrank = rank == size-1
	for za in genAZZA(start,end,np.radians(theta_res),end=lastrank):
		for az in genAZZA(0,2*np.pi,np.radians(phi_res)):
			
			#calculate the relevent wavenumber for theta,phi
			kx,ky,kz = calcWaveNumbers(obswl,np.pi/2-az,za)
			array_factor = 0+0.j
			for x,y,z in zip(xpos,ypos,zpos):
				ph = kx*x+ky*y+kz*z
				ph_target = target_kx*x+target_ky*y+target_kz*z
				array_factor += np.cos(ph-ph_target) + 1.j*np.sin(ph-ph_target)
			array_factor /= len(xpos)
			
			#tile_xpol,tile_ypol = pb.MWA_Tile_full_EE(za,az,freq=obsfreq,delays=delays,power=True,zenithnorm=True,interp=False)
			tile_xpol,tile_ypol = pb.MWA_Tile_analytic(za,az,freq=obsfreq,delays=delays,power=True,zenithnorm=True)
			tile_pattern = (tile_xpol+tile_ypol)/2.0
			
			phased_array_pattern = tile_pattern * np.abs(array_factor)**2			
			
			results.append([np.degrees(za),np.degrees(az),phased_array_pattern])

	return results

	

parser = argparse.ArgumentParser(description="""Script to calculate the array factor required to model the tied-array beam for the MWA.""",\
                                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument("-o","--obsid",type=str,action='store',metavar="obsID",\
		help="""Observation ID (used to figure out spatial configuration of array). 
			Also used to retrieve observation start-time and duration.""",default=None)
parser.add_argument("--flagged_tiles",type=str,nargs='+',action='store',metavar="tile",help="The tiles flagged as in when running the RTS. Must be a list of space separated tile numbers, e.g. 0 1 2 5",default=None)
parser.add_argument("-p","--target",type=str,nargs=2,action='store',metavar=("ra","dec"),\
		help="The RA and DEC of the target pointing (i.e the desired phase-centre). Should be formtted like: hh:mm:ss.sss dd\"mm\'ss.ssss",default=("00:00:00.0000","00:00:00.0000"))

parser.add_argument("-t","--time",type=str,action='store',metavar="time",\
		help="The UTC time to evaluate the array factor. This overrides the start-time retrieved from the observation ID metafits. Should be formatted like: yyyy-mm-dd hh:mm:ss.ssss",default=None)
parser.add_argument("-f","--freq",type=float,action='store',metavar="frequency",help="The centre observing frequency for the observation (in Hz!)",default=184.96e6)
parser.add_argument("-e","--efficiency",type=float,action='store',metavar="eta",help="Frequency and pointing dependent efficiency",default=1)
parser.add_argument("--grid_res",type=float,action='store',nargs=2,metavar=("theta_res","phi_res"),
		help="""Resolution of the (theta,phi) grid to be created in degrees per pixel. This equivaently determines the size of the (az,za) grid. 
			So, if you want 0.1 degrees per pixel in both theta and phi, then --grid_res 0.1 0.1, etc. 
			!!CAUTION!!: this can easily use up all of your available memory if you set the resolution too fine!""",default=(0.1,0.1))
#parser.add_argument("--write",action='store_true',help="Write the tied-array beam matrix to file - in FEKO-like format")
#parser.add_argument("--plotting",action='store_true',help="""Output figures of the calculated MWA beam, array factor and product (i.e. the tied-array beam).\
#								 Figures are produced in both normalised power and dB scales.\
#								 MWA beam patterns as: <obsid>_gx_<freq>MHz_<Az>_<ZA>.png,\
#							 	 array factor patterns as: <obsid>_fx_<freq>MHz_<Az>_<ZA>.png,\
#								 and the product as <obsid>_gxfx_<freq>MHz_<Az>_<ZA>.png""")
#parser.add_argument("--dB",action='store_true',help="Plot with dB scale as well as normalised power.")
#parser.add_argument("--polar",action='store_true',help="""Plot in polar coordinates. Note that the zoom option will only work nicely for zenith pointings\
#							 (due to matplotlib not being able to handle arbitrary zoom in polar mode)""")
#parser.add_argument("--zoom",action='store',type=float,nargs=2,metavar=("lo","hi"),help="""Zoom factor for Az,ZA coords. Does not apply to dB plots.\
#									 Think of these as multiplication factors on the target position.\
#									 So: --zoom 0.8 1.2 would set the x and y axis limits to (0.8*target_position, 1.2*target_position).""",default=None)
#parser.add_argument("--showtarget",action='store_true',help="When plotting, marker the target pointing")
parser.add_argument("--coplanar",action='store_true',help="Assume the array is co-planar (i.e. height above array centre is 0 for all tiles)")
parser.add_argument("--zenith",action='store_true',help="Assume zenith pointing (i.e  delays are 0), ZA = 0 and AZ = 0")
args = parser.parse_args()


ra,dec = args.target
tres,pres = args.grid_res
ntheta,nphi = 90/tres,360/pres
#if args.showtarget and not args.plotting:
#	print "!!WARNING!! ::  opted to show target location, but did not opt to plot - ignoring --showtarget option."
#	args.showtarget = False
#
#if args.polar and args.zoom:
#	print "!!WARNING!! :: currently can't use zoom with polar coords - ignoring zoom option"	
#
if args.flagged_tiles == None:
	flags = []
else:
	flags = args.flagged_tiles

if args.zenith:
	delays = [0]*16
else:
	delays = get_delay_steps(args.obsid)[4]
	
#grab the relavnt metafits file
if os.path.isfile('/scratch2/mwaops/{0}/{1}_metafits_ppds.fits'.format(os.environ['USER'],args.obsid)) is False:
	os.system('wget -O /scratch2/mwaops/{0}/{1}_metafits_ppds.fits mwa-metadata01.pawsey.org.au/metadata/fits?obs_id={0}'.format(os.environ['USER'],args.obsid))
	

# Setup stuff for MPI
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

# figure out how many chunks to split up ZA into
#print rank,size,(np.pi/2)/np.radians(tres),np.radians(tres)
totalcalcs = (np.pi/2)/np.radians(tres) #total number of calculations required
assert totalcalcs >= size, "Total calculations must be >= the number of cores available"
#print "total calcs",totalcalcs
start = rank * np.radians(tres) * (totalcalcs//size)
end = (rank+1) * np.radians(tres) * (totalcalcs//size)
if rank == size-1:
	end = np.pi/2 # give the last core anything that's left
print "worker:",rank,"total calcs:",totalcalcs
print "start ZA:",np.degrees(start),"end ZA",np.degrees(end)

# get the chunk of data for this thread
chunk = createArrayFactor(ra,dec,args.obsid,delays,args.time,args.freq,args.efficiency,flags,tres,pres,args.coplanar,args.zenith,start,end)
if args.time is None:
	time = Time(get_obstime_duration(args.obsid)[0])
oname = "/scratch2/mwaops/{0}/{1}_{2}_{3}MHz_{4}_{5}.dat".format(os.environ['USER'],args.obsid,time.gps,args.freq/1e6,ra,dec)
# write the header of the file (for FEKO compatability-ish)
#print "writing to {0}".format(oname)
#print "gathering results from workers"
if rank != 0:
	# not the master, send data back to master (node 0)
	print "sending from {0}".format(rank)
	comm.send(chunk,dest=0)
elif rank == 0:
	# I am the master, receive data from other nodes
	print "receiving at master"
	result = chunk
	# write the master node's results first
	print "writing master"
	with open(oname,"w") as f:
		f.write("##File Type: Far field\n##File Format: 3\n##Source: mwa-phased-array\n##Date: 2016-11-14 15:14:00\n** File exported by FEKO kernel version 7.0.1-482\n\n")
		f.write("#Request Name: FarField\n#Frequency: {0}\n#Coordinate System: Spherical\n".format(args.freq))
		f.write("#No. of Theta Samples: {0}\n#No. of Phi Samples: {1}\n".format(ntheta,nphi))
		f.write("#Result Type: Gain\n#No. of Header Lines: 1\n")
		f.write('#"Theta"\t"Phi"\t"Re(Etheta)"\t"Im(Etheta)"\t"Re(Ephi)"\t"Im(Ephi)"\t"Gain(Theta)"\t"Gain(Phi)"\t"Gain(Total)"\n')

		for res in result:
			f.write("{0}\t{1}\t0\t0\t0\t0\t0\t0\t{2}\n".format(res[0],res[1],res[2]))

	for i in range(1,size):
		# then write the worker nodes results
		print "writing from worker",i
		result = comm.recv(source=i)
		with open(oname,"a") as f:
			for res in result:
				f.write("{0}\t{1}\t0\t0\t0\t0\t0\t0\t{2}\n".format(res[0],res[1],res[2]))

		#result.extend(comm.recv(source=i))
	#print "final size:",np.shape(result)
		
