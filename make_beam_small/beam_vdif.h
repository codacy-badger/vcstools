#ifndef BEAM_VDIF_H
#define BEAM_VDIF_H

#include <complex.h>
#include <fftw3.h>
#include "vdifio.h"

#define  VDIF_HEADER_SIZE  32

/* convenience type - this just collects all the vdif info together */
struct vdifinfo {

    int frame_length; //length of the vdif frame
    int frame_rate; // frames per second
    size_t samples_per_frame; // number of time samples per vdif frame
    int bits; // bits per sample
    int nchan; // channels per framme
    int chan_width; // channel width in hertz
    int sample_rate;  // sample rate in hertz
    int iscomplex; // complex sample flag
    int threadid; // which thread are we
    char stationid[3]; // which station are we.
    char exp_name[17]; // Experiment name
    char scan_name[17]; // scan_name
    size_t block_size; // size of one second of output data including headers
    size_t sizeof_buffer; // size of one second of 32bit complex beam data (no headers)
    size_t sizeof_beam; // size of 1 sample of 32bit complex beam data (no headers)
    float *b_scales; // bandpass mean
    float *b_offsets; // bandpass offset

    // observation info
    char telescope[24];
    char source[24];
    char obs_mode[8];
    double fctr;

    char ra_str[16];
    char dec_str[16];

    double BW;

    long double MJD_epoch;

    char date_obs[24];
    char basefilename[1024];

    int got_scales;

};

void vdif_write_data( struct vdifinfo *vf, int8_t *output );
void vdif_write_second( struct vdifinfo *vf, vdif_header *vhdr,
        float *data_buffer_vdif, float *gain );

void populate_vdif_header(
        struct vdifinfo *vf,
        vdif_header     *vhdr,
        char            *metafits,
        char            *obsid,
        char            *time_utc,
        int              sample_rate,
        long int         frequency,
        int              nchan, 
        long int         chan_width,
        char            *rec_channel,
        struct delays   *delay_vals );

complex float get_std_dev_complex( complex float *input, int nsamples );

void set_level_occupancy( complex float *input, int nsamples,
                          float *new_gain );

void get_mean_complex( complex float *input, int nsamples, float *rmean,
                       float *imean, complex float *cmean );

void normalise_complex( complex float *input, int nsamples, float scale );

void to_offset_binary( int8_t *i, int n );

void invert_pfb_ifft( complex float *array, int nchan,
                      fftwf_plan p, fftwf_complex *in, fftwf_complex *out );

//void invert_pfb_ord( complex float *input, complex float *output,
//                     int nchan_in, int nchan_out );

#endif