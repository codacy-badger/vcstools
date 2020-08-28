/********************************************************
 *                                                      *
 * Licensed under the Academic Free License version 3.0 *
 *                                                      *
 ********************************************************/

// TODO: Remove superfluous #includes
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <math.h>
#include <unistd.h>
#include <getopt.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include "slalib.h"
#include "slamac.h"
#include "ascii_header.h"
#include "mwa_header.h"
#include <glob.h>
#include <fcntl.h>
#include <assert.h>
#include "beam_common.h"
#include "beam_psrfits.h"
#include "beam_vdif.h"
#include "make_beam.h"
#include "vdifio.h"
#include "filter.h"
#include "psrfits.h"
#include "mycomplex.h"
#include "form_beam.h"

#ifdef HAVE_CUDA

#include "ipfb.h"
double now(){
  struct timespec t;
  clock_gettime(CLOCK_REALTIME,&t);
  return (double)t.tv_sec + (double)t.tv_nsec/1000000000L;
}
#define NOW now()

#else

#include <omp.h>
#define NOW  (omp_get_wtime())

#endif

int main(int argc, char **argv)
{
#ifndef HAVE_CUDA
    // Initialise FFTW with OpenMP
    fftw_init_threads();
    fftw_plan_with_nthreads( omp_get_max_threads() );
#endif

    // A place to hold the beamformer settings
    struct make_beam_opts opts;

    /* Set default beamformer settings */

    // Variables for required options
    opts.obsid       = NULL; // The observation ID
    opts.begin       = 0;    // GPS time -- when to start beamforming
    opts.end         = 0;    // GPS time -- when to stop beamforming
    opts.time_utc    = NULL; // utc time string "yyyy-mm-ddThh:mm:ss"
    opts.dec_ddmmss  = NULL; // "dd:mm:ss"
    opts.ra_hhmmss   = NULL; // "hh:mm:ss"
    opts.datadir     = NULL; // The path to where the recombined data live
    opts.metafits    = NULL; // filename of the metafits file
    opts.rec_channel = NULL; // 0 - 255 receiver 1.28MHz channel
    opts.frequency   = 0;    // = rec_channel expressed in Hz

    // Variables for MWA/VCS configuration
    opts.nstation      = 128;    // The number of antennas
    opts.nchan         = 128;    // The number of fine channels (per coarse channel)
    opts.chan_width    = 10000;  // The bandwidth of an individual fine chanel (Hz)
    opts.sample_rate   = 10000;  // The VCS sample rate (Hz)
    opts.custom_flags  = NULL;   // Use custom list for flagging antennas

    // Output options
    opts.out_incoh     = 0;  // Default = PSRFITS (incoherent) output turned OFF
    opts.out_coh       = 0;  // Default = PSRFITS (coherent)   output turned OFF
    opts.out_vdif      = 0;  // Default = VDIF                 output turned OFF
    opts.out_uvdif     = 0;  // Default = upsampled VDIF       output turned OFF

    // Variables for calibration settings
    opts.cal.filename          = NULL;
    opts.cal.bandpass_filename = NULL;
    opts.cal.chan_width        = 40000;
    opts.cal.nchan             = 0;
    opts.cal.cal_type          = NO_CALIBRATION;
    opts.cal.offr_chan_num     = 0;

    // Parse command line arguments
    make_beam_parse_cmdline( argc, argv, &opts );

    // Create "shorthand" variables for options that are used frequently
    int nstation           = opts.nstation;
    int nchan              = opts.nchan;
    const int npol         = 2;      // (X,Y)
    const int outpol_coh   = 4;      // (I,Q,U,V)
    const int outpol_incoh = 1;      // ("I")

    float vgain = 1.0; // This is re-calculated every second for the VDIF output
    float ugain = 1.0; // This is re-calculated every second for the VDIF output

    // Start counting time from here (i.e. after parsing the command line)
    double begintime = NOW;
#ifdef HAVE_CUDA
    printf("[%f]  Starting %s with GPU acceleration\n", NOW-begintime, argv[0] );
#else
    printf("[%f]  Starting %s with %d possible OpenMP threads\n", NOW-begintime, argv[0], omp_get_max_threads());
#endif

    // Calculate the number of files
    int nfiles = opts.end - opts.begin + 1;
    if (nfiles <= 0) {
        fprintf(stderr, "Cannot beamform on %d files (between %lu and %lu)\n", nfiles, opts.begin, opts.end);
        exit(EXIT_FAILURE);
    }

    // Allocate memory
    char **filenames = create_filenames( &opts );
    ComplexDouble ***complex_weights_array = create_complex_weights( nstation, nchan, npol ); // [nstation][nchan][npol]
    ComplexDouble ****invJi = create_invJi( nstation, nchan, npol ); // [nstation][nchan][npol][npol]
    ComplexDouble ***detected_beam = create_detected_beam( 2*opts.sample_rate, nchan, npol ); // [2*opts.sample_rate][nchan][npol]

    // Read in info from metafits file
    printf("[%f]  Reading in metafits file information from %s\n", NOW-begintime, opts.metafits);
    struct metafits_info mi;
    get_metafits_info( opts.metafits, &mi, opts.chan_width );

    // If using bandpass calibration solutions, calculate number of expected bandpass channels
    if (opts.cal.cal_type == RTS_BANDPASS)
        opts.cal.nchan = (nchan * opts.chan_width) / opts.cal.chan_width;

    // If a custom flag file has been provided, use that instead of the metafits flags
    int i;
    if (opts.custom_flags != NULL)
    {
        // Reset the weights to 1
        for (i = 0; i < nstation*npol; i++)
            mi.weights_array[i] = 1.0;

        // Open custom flag file for reading
        FILE *flagfile = fopen( opts.custom_flags, "r" );
        if (flagfile == NULL)
        {
            fprintf( stderr, "error: couldn't open flag file \"%s\" for "
                             "reading\n", opts.custom_flags );
            exit(EXIT_FAILURE);
        }

        // Read in flags from file
        int nitems;
        int flag, ant;
        while (!feof(flagfile))
        {
            // Read in next item
            nitems = fscanf( flagfile, "%d", &ant );
            if (nitems != 1 && !feof(flagfile))
            {
                fprintf( stderr, "error: couldn't parse flag file \"%s\"\n",
                        opts.custom_flags );
                exit(EXIT_FAILURE);
            }

            // Flag both polarisations of the antenna in question
            flag = ant*2;
            mi.weights_array[flag]   = 0.0;
            mi.weights_array[flag+1] = 0.0;
        }

        // Close file
        fclose( flagfile );
    }

    // Issue warnings if any antennas are being used which are flagged in the metafits file
    for (i = 0; i < nstation*npol; i++)
    {
        if (mi.weights_array[i] != 0.0 &&
            mi.flag_array[i]    != 0.0)
        {
            fprintf( stderr, "warning: antenna %3d, pol %d is included even "
                             "though it is flagged in the metafits file\n",
                             i / npol,
                             i % npol );
        }
    }
    
    double wgt_sum = 0;
    for (i = 0; i < nstation*npol; i++)
        wgt_sum += mi.weights_array[i];
    double invw = 1.0/wgt_sum;

    // Run get_delays to populate the delay_vals struct
    printf("[%f]  Setting up output header information\n", NOW-begintime);
    struct delays delay_vals;
    get_delays(
            opts.dec_ddmmss,    // dec as a string "dd:mm:ss"
            opts.ra_hhmmss,     // ra  as a string "hh:mm:ss"
            opts.frequency,     // middle of the first frequency channel in Hz
            &opts.cal,          // struct holding info about calibration
            opts.sample_rate,   // = 10000 samples per sec
            opts.time_utc,      // utc time string
            0.0,                // seconds offset from time_utc at which to calculate delays
            &delay_vals,        // Populate psrfits header info
            &mi,                // Struct containing info from metafits file
            NULL,               // complex weights array (ignore this time)
            NULL                // invJi array           (ignore this time)
    );

    // Create structures for holding header information
    struct psrfits  pf;
    struct psrfits  pf_incoh;
    vdif_header     vhdr;
    vdif_header     uvhdr;
    struct vdifinfo vf;
    struct vdifinfo uvf;

    // Create structures for the PFB filter coefficients
    int ntaps    = 12;
    int fil_size = ntaps * nchan; // = 12 * 128 = 1536
    double coeffs[] = FINE_PFB_FILTER_COEFFS; // Hardcoded 1536 numbers
    ComplexDouble fil[fil_size];
    double approx_filter_scale = 1.0/120000.0;
    for (i = 0; i < fil_size; i++)
    {
        fil[i] = CMaked( coeffs[i] * approx_filter_scale, 0.0 );
    }

    // Memory for fil_ramps is allocated here:
    ComplexDouble **fil_ramps = apply_mult_phase_ramps( fil, fil_size, nchan );

    // Populate the relevant header structs
    populate_psrfits_header( &pf, opts.metafits, opts.obsid, opts.time_utc,
            opts.sample_rate, opts.frequency, nchan, opts.chan_width,
            outpol_coh, opts.rec_channel, &delay_vals );
    populate_psrfits_header( &pf_incoh, opts.metafits, opts.obsid,
            opts.time_utc, opts.sample_rate, opts.frequency, nchan,
            opts.chan_width, outpol_incoh, opts.rec_channel, &delay_vals );

    // Use the tile pointing instead of the pencil beam pointing
    // TO DO: Move this to populate_psrfits_header?
    pf_incoh.hdr.ra2000  = mi.tile_pointing_ra;
    pf_incoh.hdr.dec2000 = mi.tile_pointing_dec;

    populate_vdif_header( &vf, &vhdr, opts.metafits, opts.obsid,
            opts.time_utc, opts.sample_rate, opts.frequency, nchan,
            opts.chan_width, opts.rec_channel, &delay_vals );
    populate_vdif_header( &uvf, &uvhdr, opts.metafits, opts.obsid,
            opts.time_utc, opts.sample_rate, opts.frequency, nchan,
            opts.chan_width, opts.rec_channel, &delay_vals );

    sprintf( uvf.basefilename, "%s_%s_ch%03d_u",
             uvf.exp_name, uvf.scan_name, atoi(opts.rec_channel) );

    // Create array for holding the raw data
    int bytes_per_file = opts.sample_rate * nstation * npol * nchan;
    uint8_t *data = (uint8_t *)malloc( bytes_per_file * sizeof(uint8_t) );
    assert(data);

    // Create output buffer arrays
    float *data_buffer_coh   = NULL;
    float *data_buffer_incoh = NULL;
    float *data_buffer_vdif  = NULL;
    float *data_buffer_uvdif = NULL;

    data_buffer_coh   = create_data_buffer_psrfits( nchan * outpol_coh * pf.hdr.nsblk );
    data_buffer_incoh = create_data_buffer_psrfits( nchan * outpol_incoh * pf_incoh.hdr.nsblk );
    data_buffer_vdif  = create_data_buffer_vdif( &vf );
    data_buffer_uvdif = create_data_buffer_vdif( &uvf );

    /* Allocate host and device memory for the use of the cu_form_beam function */
    struct gpu_formbeam_arrays gf;
    struct gpu_ipfb_arrays gi;
#ifdef HAVE_CUDA
    malloc_formbeam( &gf, opts.sample_rate, nstation, nchan, npol,
            outpol_coh, outpol_incoh );

    if (opts.out_uvdif)
    {
        malloc_ipfb( &gi, ntaps, opts.sample_rate, nchan, npol, fil_size );
        cu_load_filter( fil_ramps, &gi, nchan );
    }
#endif

    double read_time[nfiles], delay_time[nfiles], calc_time[nfiles], write_time[nfiles];
    double start;
    int file_no = 0;

    printf("[%f]  **BEGINNING BEAMFORMING**\n", NOW-begintime);
    for (file_no = 0; file_no < nfiles; file_no++) {

        // Read in data from next file
        start = NOW;
        printf("[%f]  Reading in data from %s [%d/%d]\n", NOW-begintime,
                filenames[file_no], file_no+1, nfiles);
        read_data( filenames[file_no], data, bytes_per_file  );
        read_time[file_no] = NOW - start;

        // Get the next second's worth of phases / jones matrices, if needed
        start = NOW;
        printf("[%f]  Calculating delays\n", NOW-begintime);
        get_delays(
                opts.dec_ddmmss,        // dec as a string "dd:mm:ss"
                opts.ra_hhmmss,         // ra  as a string "hh:mm:ss"
                opts.frequency,         // middle of the first frequency channel in Hz
                &opts.cal,              // struct holding info about calibration
                opts.sample_rate,       // = 10000 samples per sec
                opts.time_utc,          // utc time string
                (double)file_no,        // seconds offset from time_utc at which to calculate delays
                NULL,                   // Don't update delay_vals
                &mi,                    // Struct containing info from metafits file
                complex_weights_array,  // complex weights array (answer will be output here)
                invJi );                // invJi array           (answer will be output here)
        delay_time[file_no] = NOW - start;

        printf("[%f]  Calculating beam\n", NOW-begintime);
        start = NOW;

        for (i = 0; i < nchan * outpol_coh * pf.hdr.nsblk; i++)
            data_buffer_coh[i] = 0.0;

        for (i = 0; i < nchan * outpol_incoh * pf_incoh.hdr.nsblk; i++)
            data_buffer_incoh[i] = 0.0;

#ifdef HAVE_CUDA
        cu_form_beam( data, &opts, complex_weights_array, invJi, file_no,
                      nstation, nchan, npol, outpol_coh, invw, &gf,
                      detected_beam, data_buffer_coh, data_buffer_incoh );
#else
        form_beam( data, &opts, complex_weights_array, invJi, file_no,
                   nstation, nchan, npol, outpol_coh, outpol_incoh, invw,
                   detected_beam, data_buffer_coh, data_buffer_incoh );
#endif

        // Invert the PFB, if requested
        if (opts.out_vdif)
        {
            printf("[%f]  Inverting the PFB (IFFT)\n", NOW-begintime);
#ifndef HAVE_CUDA
            invert_pfb_ifft( detected_beam, file_no, opts.sample_rate, nchan,
                    npol, data_buffer_vdif );
#endif
        }

        if (opts.out_uvdif)
        {
            printf("[%f]  Inverting the PFB (full)\n", NOW-begintime);
#ifdef HAVE_CUDA
            cu_invert_pfb_ord( detected_beam, file_no, opts.sample_rate,
                    nchan, npol, &gi, data_buffer_uvdif );
#else
            invert_pfb_ord( detected_beam, file_no, opts.sample_rate, nchan,
                    npol, fil_ramps, fil_size, data_buffer_uvdif );
#endif
        }
        calc_time[file_no] = NOW - start;

        printf("[%f]  Writing data to file(s)\n", NOW-begintime);
        start = NOW;

        if (opts.out_coh)
            psrfits_write_second( &pf, data_buffer_coh, nchan, outpol_coh );
        if (opts.out_incoh)
            psrfits_write_second( &pf_incoh, data_buffer_incoh, nchan, outpol_incoh );
        if (opts.out_vdif)
            vdif_write_second( &vf, &vhdr, data_buffer_vdif, &vgain );
        if (opts.out_uvdif)
            vdif_write_second( &uvf, &uvhdr, data_buffer_uvdif, &ugain );
        write_time[file_no] = NOW - start;
    }

    printf("[%f]  **FINISHED BEAMFORMING**\n", NOW-begintime);

    // Calculate total processing times
    double read_sum = 0, delay_sum = 0, calc_sum = 0, write_sum = 0;
    for (file_no = 0; file_no < nfiles; file_no++)
    {
        read_sum  += read_time[file_no];
        delay_sum += delay_time[file_no];
        calc_sum  += calc_time[file_no];
        write_sum += write_time[file_no];
    }
    double read_mean, delay_mean, calc_mean, write_mean;
    read_mean  = read_sum  / nfiles;
    delay_mean = delay_sum / nfiles;
    calc_mean  = calc_sum  / nfiles;
    write_mean = write_sum / nfiles;

    // Calculate the standard deviations
    double read_std = 0, delay_std = 0, calc_std = 0, write_std = 0;
    for (file_no = 0; file_no < nfiles; file_no++)
    {
        read_std  += pow(read_time[file_no]  - read_mean,  2);
        delay_std += pow(delay_time[file_no] - delay_mean, 2);
        calc_std  += pow(calc_time[file_no]  - calc_mean,  2);
        write_std += pow(write_time[file_no] - write_mean, 2);
    }
    read_std  = sqrt( read_std  / nfiles );
    delay_std = sqrt( delay_std / nfiles );
    calc_std  = sqrt( calc_std  / nfiles );
    write_std = sqrt( write_std / nfiles );


    fprintf( stderr, "[%f]  **FINISHED BEAMFORMING**\n", NOW-begintime );
    fprintf( stderr, "[%f]  Total read  processing time: %9.3f s\n",
                     NOW-begintime, read_sum );
    fprintf( stderr, "[%f]  Mean  read  processing time: %9.3f +\\- %8.3f s\n",
                     NOW-begintime, read_mean, read_std );
    fprintf( stderr, "[%f]  Total delay processing time: %9.3f s\n",
                     NOW-begintime, delay_sum );
    fprintf( stderr, "[%f]  Mean  delay processing time: %9.3f +\\- %8.3f s\n",
                     NOW-begintime, delay_mean, delay_std );
    fprintf( stderr, "[%f]  Total calc  processing time: %9.3f s\n",
                     NOW-begintime, calc_sum );
    fprintf( stderr, "[%f]  Mean  calc  processing time: %9.3f +\\- %8.3f s\n",
                     NOW-begintime, calc_mean, calc_std );
    fprintf( stderr, "[%f]  Total write processing time: %9.3f s\n",
                     NOW-begintime, write_sum  );
    fprintf( stderr, "[%f]  Mean  write processing time: %9.3f +\\- %8.3f s\n",
                     NOW-begintime, write_mean, write_std );



    printf("[%f]  Starting clean-up\n", NOW-begintime);

    // Free up memory
    destroy_filenames( filenames, &opts );
    destroy_complex_weights( complex_weights_array, nstation, nchan );
    destroy_invJi( invJi, nstation, nchan, npol );
    destroy_detected_beam( detected_beam, 2*opts.sample_rate, nchan );

    int ch;
    for (ch = 0; ch < nchan; ch++)
    {
        free( fil_ramps[ch] );
    }
    free( fil_ramps );

    destroy_metafits_info( &mi );
    free( data_buffer_coh   );
    free( data_buffer_incoh );
    free( data_buffer_vdif  );
    free( data_buffer_uvdif );
    free( data );

    free( opts.obsid        );
    free( opts.time_utc     );
    free( opts.dec_ddmmss   );
    free( opts.ra_hhmmss    );
    free( opts.datadir      );
    free( opts.metafits     );
    free( opts.rec_channel  );
    free( opts.cal.filename );
    free( opts.custom_flags );

    if (opts.out_coh)
    {
        free( pf.sub.data        );
        free( pf.sub.dat_freqs   );
        free( pf.sub.dat_weights );
        free( pf.sub.dat_offsets );
        free( pf.sub.dat_scales  );
    }
    if (opts.out_incoh)
    {
        free( pf_incoh.sub.data        );
        free( pf_incoh.sub.dat_freqs   );
        free( pf_incoh.sub.dat_weights );
        free( pf_incoh.sub.dat_offsets );
        free( pf_incoh.sub.dat_scales  );
    }
    if (opts.out_vdif)
    {
        free( vf.b_scales  );
        free( vf.b_offsets );
    }
    if (opts.out_uvdif)
    {
        free( uvf.b_scales  );
        free( uvf.b_offsets );
    }

#ifdef HAVE_CUDA
    free_formbeam( &gf );
    if (opts.out_uvdif)
        free_ipfb( &gi );
#endif

#ifndef HAVE_CUDA
    // Clean up FFTW OpenMP
    fftw_cleanup_threads();
#endif

    return 0;
}


void usage() {
    fprintf(stderr, "\n");
    fprintf(stderr, "usage: make_beam [OPTIONS]\n");

    fprintf(stderr, "\n");
    fprintf(stderr, "REQUIRED OPTIONS\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-o, --obsid=GPSTIME       ");
    fprintf(stderr, "Observation ID (GPS seconds).\n");
    fprintf(stderr, "\t-b, --begin=GPSTIME       ");
    fprintf(stderr, "Begin time of observation, in GPS seconds\n");
    fprintf(stderr, "\t-e, --end=GPSTIME         ");
    fprintf(stderr, "End time of observation, in GPS seconds\n");
    fprintf(stderr, "\t-z, --utc-time=UTCTIME    ");
    fprintf(stderr, "The UTC time that corresponds to the GPS time given by the -b\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "option. UTCTIME must have the format: yyyy-mm-ddThh:mm:ss\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-D, --dec=dd:mm:ss.s      ");
    fprintf(stderr, "Declination of pointing direction\n");
    fprintf(stderr, "\t-R, --ra=hh:mm:ss.s       ");
    fprintf(stderr, "Right ascension of pointing direction\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-d, --data-location=PATH  ");
    fprintf(stderr, "PATH is the directory containing the recombined data\n");
    fprintf(stderr, "\t-m, --metafits-file=FILE  ");
    fprintf(stderr, "FILE is the metafits file pertaining to the OBSID given by the\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr,  "-o option\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-f, --coarse-chan=N       ");
    fprintf(stderr, "Absolute coarse channel number (0-255)\n");

    fprintf(stderr, "\n");
    fprintf(stderr, "OUTPUT OPTIONS\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-i, --incoh                ");
    fprintf(stderr, "Turn on incoherent PSRFITS beam output.                          ");
    fprintf(stderr, "[default: OFF]\n");
    fprintf(stderr, "\t-p, --psrfits              ");
    fprintf(stderr, "Turn on coherent PSRFITS output (will be turned on if none of\n");
    fprintf(stderr, "\t                           ");
    fprintf(stderr, "-i, -p, -u, -v are chosen).                                      ");
    fprintf(stderr, "[default: OFF]\n");
    fprintf(stderr, "\t-u, --uvdif                ");
    fprintf(stderr, "Turn on VDIF output with upsampling                              ");
    fprintf(stderr, "[default: OFF]\n");
    fprintf(stderr, "\t-v, --vdif                 ");
    fprintf(stderr, "Turn on VDIF output without upsampling                           ");
    fprintf(stderr, "[default: OFF]\n");

    fprintf(stderr, "\n");
    fprintf(stderr, "MWA/VCS CONFIGURATION OPTIONS\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-a, --antennas=N          ");
    fprintf(stderr, "The number of antennas in the array. For MWA Phase 2, N=128.     ");
    fprintf(stderr, "[default: 128]\n");
    fprintf(stderr, "\t-n, --num-fine-chans=N    ");
    fprintf(stderr, "The number of fine channels per coarse channel.                  ");
    fprintf(stderr, "[default: 128]\n");
    fprintf(stderr, "\t-w, --fine-chan-width=N   ");
    fprintf(stderr, "The bandwidth of an individual fine channel (Hz).                ");
    fprintf(stderr, "[default: 10000]\n");
    fprintf(stderr, "\t-r, --sample-rate=N       ");
    fprintf(stderr, "The VCS sample rate, in Hz. (The sample rate given in the meta-  ");
    fprintf(stderr, "[default: 10000]\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "metafits file matches the correlator settings at the time of\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "the observation, which is not necessarily the same as that of\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "the VCS. Hence the necessity of this option.)\n");
    fprintf(stderr, "\t-F, --custom-flags=file   ");
    fprintf(stderr, "Flag the antennas listed in file instead of those flagged in the ");
    fprintf(stderr, "[default: none]\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "metafits file given by the -m option.\n");

    fprintf(stderr, "\n");
    fprintf(stderr, "CALIBRATION OPTIONS (RTS)\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-J, --dijones-file=PATH   ");
    fprintf(stderr, "The direction-independent Jones matrix file that is output from\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "the RTS. Using this option instructs the beamformer to use the\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "RTS-generated calibration solution. Either -J or -O must be\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "supplied. If both are supplied the one that comes last will\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "override the former.\n");
    fprintf(stderr, "\t-B, --bandpass-file=PATH  ");
    fprintf(stderr, "The bandpass file that is output from the RTS. If this option\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "is given, the RTS calibration solution will be applied to each\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "fine channel. If -J is supplied but -B is not, then the coarse\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "channel solution will be applied to ALL fine channels\n");
    fprintf(stderr, "\t-W, --rts-chan-width      ");
    fprintf(stderr, "RTS calibration channel bandwidth (Hz)                           ");
    fprintf(stderr, "[default: 40000]\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "CALIBRATION OPTIONS (OFFRINGA)\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-O, --offringa-file=PATH  ");
    fprintf(stderr, "The calibration solution file that is output from the tools\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "made by Andre Offringa. Using this option instructs the beam-\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "former to use the Offringa-style calibration solution. Either\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "-J or -O must be supplied. If both are supplied the one that\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "comes last will override the former.\n");
    fprintf(stderr, "\t-C, --offringa-chan=N     ");
    fprintf(stderr, "The zero-offset position of the coarse channel solution in the   ");
    fprintf(stderr, "[default: 0]\n");
    fprintf(stderr, "\t                          ");
    fprintf(stderr, "calibration file given by the -O option.\n");

    fprintf(stderr, "\n");
    fprintf(stderr, "OTHER OPTIONS\n");
    fprintf(stderr, "\n");
    fprintf(stderr, "\t-h, --help                ");
    fprintf(stderr, "Print this help and exit\n");
    fprintf(stderr, "\t-V, --version             ");
    fprintf(stderr, "Print version number and exit\n");
    fprintf(stderr, "\n");
}



void make_beam_parse_cmdline(
        int argc, char **argv, struct make_beam_opts *opts )
{
    if (argc > 1) {

        int c;
        while (1) {

            static struct option long_options[] = {
                {"obsid",           required_argument, 0, 'o'},
                {"begin",           required_argument, 0, 'b'},
                {"end",             required_argument, 0, 'e'},
                {"incoh",           no_argument,       0, 'i'},
                {"psrfits",         no_argument,       0, 'p'},
                {"vdif",            no_argument,       0, 'v'},
                {"utc-time",        required_argument, 0, 'z'},
                {"dec",             required_argument, 0, 'D'},
                {"ra",              required_argument, 0, 'R'},
                {"data-location",   required_argument, 0, 'd'},
                {"metafits-file",   required_argument, 0, 'm'},
                {"coarse-chan",     required_argument, 0, 'f'},
                {"antennas",        required_argument, 0, 'a'},
                {"num-fine-chans",  required_argument, 0, 'n'},
                {"fine-chan-width", required_argument, 0, 'w'},
                {"sample-rate",     required_argument, 0, 'r'},
                {"custom-flags",    required_argument, 0, 'F'},
                {"dijones-file",    required_argument, 0, 'J'},
                {"bandpass-file",   required_argument, 0, 'B'},
                {"rts-chan-width",  required_argument, 0, 'W'},
                {"offringa-file",   required_argument, 0, 'O'},
                {"offringa-chan",   required_argument, 0, 'C'},
                {"help",            required_argument, 0, 'h'},
                {"version",         required_argument, 0, 'V'}
            };

            int option_index = 0;
            c = getopt_long( argc, argv,
                             "a:b:B:C:d:D:e:f:F:hiJ:m:n:o:O:pr:R:uvVw:W:z:",
                             long_options, &option_index);
            if (c == -1)
                break;

            switch(c) {

                case 'a':
                    opts->nstation = atoi(optarg);
                    break;
                case 'b':
                    opts->begin = atol(optarg);
                    break;
                case 'B':
                    opts->cal.bandpass_filename = strdup(optarg);
                    opts->cal.cal_type = RTS_BANDPASS;
                    break;
                case 'C':
                    opts->cal.offr_chan_num = atoi(optarg);
                    break;
                case 'd':
                    opts->datadir = strdup(optarg);
                    break;
                case 'D':
                    opts->dec_ddmmss = strdup(optarg);
                    break;
                case 'e':
                    opts->end = atol(optarg);
                    break;
                case 'f':
                    opts->rec_channel = strdup(optarg);
                    // The base frequency of the coarse channel in Hz
                    opts->frequency = atoi(optarg) * 1.28e6 - 640e3;
                    break;
                case 'F':
                    opts->custom_flags = strdup(optarg);
                    break;
                case 'h':
                    usage();
                    exit(0);
                    break;
                case 'i':
                    opts->out_incoh = 1;
                    break;
                case 'J':
                    opts->cal.filename = strdup(optarg);
                    if (opts->cal.cal_type != RTS_BANDPASS)
                        opts->cal.cal_type = RTS;
                    break;
                case 'm':
                    opts->metafits = strdup(optarg);
                    break;
                case 'n':
                    opts->nchan = atoi(optarg);
                    break;
                case 'o':
                    opts->obsid = strdup(optarg);
                    break;
                case 'O':
                    opts->cal.filename = strdup(optarg);
                    opts->cal.cal_type = OFFRINGA;
                    break;
                case 'p':
                    opts->out_coh = 1;
                    break;
                case 'r':
                    opts->sample_rate = atoi(optarg);
                    break;
                case 'R':
                    opts->ra_hhmmss = strdup(optarg);
                    break;
                case 'u':
                    opts->out_uvdif = 1;
                    break;
                case 'v':
                    opts->out_vdif = 1;
                    break;
                case 'V':
                    printf("MWA Beamformer v%s\n", VERSION_BEAMFORMER);
                    exit(0);
                    break;
                case 'w':
                    opts->chan_width = atoi(optarg);
                    break;
                case 'W':
                    opts->cal.chan_width = atoi(optarg);
                    break;
                case 'z':
                    opts->time_utc = strdup(optarg);
                    break;
                default:
                    fprintf(stderr, "error: make_beam_parse_cmdline: "
                                    "unrecognised option '%s'\n", optarg);
                    usage();
                    exit(EXIT_FAILURE);
            }
        }
    }
    else {
        usage();
        exit(EXIT_FAILURE);
    }

#ifdef HAVE_CUDA
    // At the moment, -v is not implemented if CUDA is available
    if (opts->out_vdif)
    {
        fprintf( stderr, "error: -v is not available in the CUDA version. "
                         "To use -v, please recompile without CUDA.\n" );
        exit(EXIT_FAILURE);
    }
#endif

    // Check that all the required options were supplied
    assert( opts->obsid        != NULL );
    assert( opts->begin        != 0    );
    assert( opts->end          != 0    );
    assert( opts->time_utc     != NULL );
    assert( opts->dec_ddmmss   != NULL );
    assert( opts->ra_hhmmss    != NULL );
    assert( opts->datadir      != NULL );
    assert( opts->metafits     != NULL );
    assert( opts->rec_channel  != NULL );
    assert( opts->cal.cal_type != NO_CALIBRATION );

    // If neither -i, -p, nor -v were chosen, set -p by default
    if ( !opts->out_incoh && !opts->out_coh &&
         !opts->out_vdif  && !opts->out_uvdif )
    {
        opts->out_coh = 1;
    }
}



char **create_filenames( struct make_beam_opts *opts )
{
    // Calculate the number of files
    int nfiles = opts->end - opts->begin + 1;
    if (nfiles <= 0) {
        fprintf( stderr, "Cannot beamform on %d files (between %lu and %lu)\n",
                 nfiles, opts->begin, opts->end);
        exit(EXIT_FAILURE);
    }

    // Allocate memory for the file name list
    char **filenames = NULL;
    filenames = (char **)malloc( nfiles*sizeof(char *) );

    // Allocate memory and write filenames
    int second;
    unsigned long int timestamp;
    for (second = 0; second < nfiles; second++) {
        timestamp = second + opts->begin;
        filenames[second] = (char *)malloc( MAX_COMMAND_LENGTH*sizeof(char) );
        sprintf( filenames[second], "%s/%s_%ld_ch%s.dat",
                 opts->datadir, opts->obsid, timestamp, opts->rec_channel );
    }

    return filenames;
}


void destroy_filenames( char **filenames, struct make_beam_opts *opts )
{
    int nfiles = opts->end - opts->begin + 1;
    int second;
    for (second = 0; second < nfiles; second++)
        free( filenames[second] );
    free( filenames );
}


ComplexDouble ***create_complex_weights( int nstation, int nchan, int npol )
// Allocate memory for complex weights matrices
{
    int ant, ch; // Loop variables
    ComplexDouble ***array;
    
    array = (ComplexDouble ***)malloc( nstation * sizeof(ComplexDouble **) );

    for (ant = 0; ant < nstation; ant++)
    {
        array[ant] = (ComplexDouble **)malloc( nchan * sizeof(ComplexDouble *) );

        for (ch = 0; ch < nchan; ch++)
            array[ant][ch] = (ComplexDouble *)malloc( npol * sizeof(ComplexDouble) );
    }

    return array;
}


void destroy_complex_weights( ComplexDouble ***array, int nstation, int nchan )
{
    int ant, ch;
    for (ant = 0; ant < nstation; ant++)
    {
        for (ch = 0; ch < nchan; ch++)
            free( array[ant][ch] );

        free( array[ant] );
    }

    free( array );
}


ComplexDouble ****create_invJi( int nstation, int nchan, int npol )
// Allocate memory for (inverse) Jones matrices
{
    int ant, p, ch; // Loop variables
    ComplexDouble ****invJi;

    invJi = (ComplexDouble ****)malloc( nstation * sizeof(ComplexDouble ***) );

    for (ant = 0; ant < nstation; ant++)
    {
        invJi[ant] =(ComplexDouble ***)malloc( nchan * sizeof(ComplexDouble **) );

        for (ch = 0; ch < nchan; ch++)
        {
            invJi[ant][ch] = (ComplexDouble **)malloc( npol * sizeof(ComplexDouble *) );

            for (p = 0; p < npol; p++)
                invJi[ant][ch][p] = (ComplexDouble *)malloc( npol * sizeof(ComplexDouble) );
        }
    }

    return invJi;
}


void destroy_invJi( ComplexDouble ****array, int nstation, int nchan, int npol )
{
    int ant, ch, p;
    for (ant = 0; ant < nstation; ant++)
    {
        for (ch = 0; ch < nchan; ch++)
        {
            for (p = 0; p < npol; p++)
                free( array[ant][ch][p] );

            free( array[ant][ch] );
        }

        free( array[ant] );
    }

    free( array );
}


ComplexDouble ***create_detected_beam( int nsamples, int nchan, int npol )
// Allocate memory for complex weights matrices
{
    int s, ch; // Loop variables
    ComplexDouble ***array;
    
    array = (ComplexDouble ***)malloc( nsamples * sizeof(ComplexDouble **) );

    for (s = 0; s < nsamples; s++)
    {
        array[s] = (ComplexDouble **)malloc( nchan * sizeof(ComplexDouble *) );

        for (ch = 0; ch < nchan; ch++)
            array[s][ch] = (ComplexDouble *)malloc( npol * sizeof(ComplexDouble) );
    }

    return array;
}


void destroy_detected_beam( ComplexDouble ***array, int nsamples, int nchan )
{
    int s, ch;
    for (s = 0; s < nsamples; s++)
    {
        for (ch = 0; ch < nchan; ch++)
            free( array[s][ch] );

        free( array[s] );
    }

    free( array );
}


float *create_data_buffer_psrfits( size_t size )
{
    float *ptr = (float *)malloc( size * sizeof(float) );
    return ptr;
}


float *create_data_buffer_vdif( struct vdifinfo *vf )
{
    float *ptr  = (float *)malloc( vf->sizeof_buffer * sizeof(float) );
    return ptr;
}

