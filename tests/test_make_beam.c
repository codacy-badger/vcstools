/********************************************************
 *                                                      *
 * Licensed under the Academic Free License version 3.0 *
 *                                                      *
 ********************************************************/

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <math.h>
#include "../make_beam/mycomplex.h"
#include "slalib.h"
#include "slamac.h"
#include "psrfits.h"
#include "fitsio.h"
#include <string.h>
#include "../make_beam/beam_common.h"

#define MWA_LAT -26.703319        // Array latitude. degrees North
#define MWA_LON 116.67081         // Array longitude. degrees East
#define MWA_HGT 377               // Array altitude. meters above sea level
#define MAXREQUEST 3000000
#define NCHAN   128
#define NANT    128
#define NPOL    2
#define VLIGHT 299792458.0        // speed of light. m/s

//=====================//

int compare_2x2cmplx( ComplexDouble *M1, ComplexDouble *M2, double tol );
void print_2x2cmplx( ComplexDouble *M );
void print_2x2cmplx_compare( ComplexDouble *M1, ComplexDouble *M2 );

int compare_2x2double( double *M1, double *M2, double tol );
void print_2x2double( double *M );
void print_2x2double_compare( double *M1, double *M2 );

void test_calcEjones_analytic();
void test_parallactic_angle_correction();
void test_hash_dipole_config();

int status;

int main()
{
    status = EXIT_SUCCESS;
    test_calcEjones_analytic();
    test_parallactic_angle_correction();
    test_hash_dipole_config();
    return status;
}

void test_hash_dipole_config()
{
    int npassed = 0;
    int ntests = 5;
    double amps1[] = { 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
                       1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0 };
    double amps2[] = { 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0,
                       1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0 };
    double amps3[] = { 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0,
                       1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0 };
    double amps4[] = { 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
                       1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0 };
    double amps5[] = { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                       0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 };
    double *amps[ntests];
    amps[0] = amps1;
    amps[1] = amps2;
    amps[2] = amps3;
    amps[3] = amps4;
    amps[4] = amps5;
    int idx[ntests], ans[ntests];
    ans[0] = 0;
    ans[1] = 4;
    ans[2] = 23;
    ans[3] = 131;
    ans[4] = 137;

    // Test #1 -- all dipoles active
    int t;
    for (t = 0; t < ntests; t++)
    {
        idx[t] = hash_dipole_config( amps[t] );
        npassed += (idx[t] == ans[t]);
    }

    if (npassed != ntests)
    {
        printf( "test_hash_dipole_config failed:\n" );
        printf( "\tresults: %3d, %3d, %3d, %3d, %3d\n",
                idx[0], idx[1], idx[2], idx[3], idx[4] );
        printf( "\tanswers: %3d, %3d, %3d, %3d, %3d\n",
                ans[0], ans[1], ans[2], ans[3], ans[4] );
        status = EXIT_FAILURE;
    }
    printf( "test_hash_dipole_config passed %d/%d tests\n", npassed, ntests );
}

void test_calcEjones_analytic()
{
    int npassed = 0;
    int ntests = 0;
    double tol;      // tolerance
    ComplexDouble response[MAX_POLS];
    ComplexDouble answer[MAX_POLS];

    // Test #1
    ntests++;
    calcEjones_analytic(
            response,        // <-- answer goes here
            152660000,       // observing frequency of fine channel (Hz)
           -0.466060837760,  // observing latitude (radians)
            0.197394993071,  // azimuth & zenith angle of tile pointing
            0.649164743304,
            0.242235173094,  // azimuth & zenith angle to sample
            0.618043426835);
    answer[0] = CMaked( 0.702145873359, 0.000000000000);
    answer[1] = CMaked(-0.053699555622, 0.000000000000);
    answer[2] = CMaked(-0.016286015151, 0.000000000000);
    answer[3] = CMaked( 0.843308339933, 0.000000000000);

    tol = 1e-8;

    if (compare_2x2cmplx( response, answer, tol ))
        npassed++;
    else
    {
        printf( "test_calcEjones_analytic (test %d) failed:\n", ntests );
        print_2x2cmplx_compare( response, answer );
        status = EXIT_FAILURE;
    }

    printf( "test_calcEJones_analytic() passed %d/%d tests\n", npassed, ntests );
}

void test_parallactic_angle_correction()
{
    int npassed = 0;
    int ntests = 0;
    double tol;      // tolerance
    double answer[MAX_POLS];
    double output[MAX_POLS];

    // Test #1
    ntests++;

    parallactic_angle_correction(
        output,                // output Jones matrix
        -0.4537856055185257,   // observing latitude (radians)
        0.5235987755982988,    // azimuth angle (radians)
        0.17453292519943295);  // zenith angle (radians)

    answer[0] = -0.882365947476;
    answer[1] =  0.470563847671;
    answer[2] = -0.470563847671;
    answer[3] = -0.882365947476;

    tol = 1e-8;

    if (compare_2x2double( output, answer, tol ))
        npassed++;
    else
    {
        printf( "test_parallactic_angle_correction (test %d) failed:\n", ntests );
        print_2x2double_compare( output, answer );
        status = EXIT_FAILURE;
    }

    // Test #2
    ntests++;

    parallactic_angle_correction(
        output,                // output rotation matrix
        -0.8726646259971648,   // observing latitude (radians)
        4.468042885105484,     // azimuth angle (radians)
        0.7853981633974483);   // zenith angle (radians)

    answer[0] = -0.569146527853;
    answer[1] = -0.822236115622;
    answer[2] =  0.822236115622;
    answer[3] = -0.569146527853;

    tol = 1e-8;

    if (compare_2x2double( output, answer, tol ))
        npassed++;
    else
    {
        printf( "test_parallactic_angle_correction (test %d) failed:\n", ntests );
        print_2x2double_compare( output, answer );
        status = EXIT_FAILURE;
    }

    printf( "test_parallactic_angle_correction() passed %d/%d tests\n", npassed, ntests );
}

int compare_2x2cmplx( ComplexDouble *M1, ComplexDouble *M2, double tol )
/* Compares the real & imag parts of M1 and M2, element-wise.
 * M1 & M2 are both assumed to be 1D arrays with MAX_POLS elements.
 * Returns 0 (= fail) iff either the real or imag part of at least one element
 * differs by more than TOL; returns 1 (= success) otherwise.
 */
{
    int passed = 1;
    int i;
    for (i = 0; i < MAX_POLS; i++)
    {
        if ((fabs(CReald(M1[i]) - CReald(M2[i]))) > tol ||
            (fabs(CImagd(M1[i]) - CImagd(M2[i]))) > tol)
           {
               passed = 0;
           }
    }

    return passed;
}

void print_2x2cmplx( ComplexDouble *M )
{
    printf( "[ %.12lf%+.12lfi, %.12lf%+.12lfi, %.12lf%+.12lfi, %.12lf%+.12lfi ]",
            CReald(M[0]), CImagd(M[0]),
            CReald(M[1]), CImagd(M[1]),
            CReald(M[2]), CImagd(M[2]),
            CReald(M[3]), CImagd(M[3]) );
}

void print_2x2cmplx_compare( ComplexDouble *M1, ComplexDouble *M2 )
{
    printf( "Result  = " );
    print_2x2cmplx( M1 );
    printf( "\nCorrect = " );
    print_2x2cmplx( M2 );
    printf( "\n" );
}

int compare_2x2double( double *M1, double *M2, double tol )
/* Compares the real & imag parts of M1 and M2, element-wise.
 * M1 & M2 are both assumed to be 1D arrays with MAX_POLS elements.
 * Returns 0 (= fail) iff either the real or imag part of at least one element
 * differs by more than TOL; returns 1 (= success) otherwise.
 */
{
    int passed = 1;
    int i;
    for (i = 0; i < MAX_POLS; i++)
    {
        if ((fabs(M1[i] - M2[i])) > tol ||
            (fabs(M1[i] - M2[i])) > tol)
           {
               passed = 0;
           }
    }

    return passed;
}

void print_2x2double( double *M )
{
    printf( "[ %+.12lf, %+.12lf, %+.12lf, %+.12lf ]",
            M[0], M[1], M[2], M[3]);
}

void print_2x2double_compare( double *M1, double *M2 )
{
    printf( "Result  = " );
    print_2x2double( M1 );
    printf( "\nCorrect = " );
    print_2x2double( M2 );
    printf( "\n" );
}

