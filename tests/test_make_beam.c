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

void test_calcEjones_analytic();

int main()
{
    test_calcEjones_analytic();
    return EXIT_SUCCESS;
}

void test_calcEjones_analytic()
{
    int npassed = 0;
    int ntests = 0;
    int passed; // 1 = pass, 0 = fail
    int i; // generic array/loop index
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

    passed = 1;
    for (i = 0; i < MAX_POLS; i++)
    {
        if ((fabs(CReald(response[i])) - fabs(CReald(answer[i])) > 1e-8) ||
            (fabs(CImagd(response[i])) - fabs(CReald(answer[i])) > 1e-8))
           {
               passed = 0;
           }
    }

    if (passed)
        npassed++;
    else
    {
        printf( "test_calcEjones_analytic (test %d) failed:\n"
                "Result  = [ %f%+f, %f%+f, %f%+f, %f%+f ]\n"
                "Correct = [ %f%+f, %f%+f, %f%+f, %f%+f ]\n",
                ntests,
                CReald(response[0]), CImagd(response[0]),
                CReald(response[1]), CImagd(response[1]),
                CReald(response[2]), CImagd(response[2]),
                CReald(response[3]), CImagd(response[3]),
                CReald(answer[0]), CImagd(answer[0]),
                CReald(answer[1]), CImagd(answer[1]),
                CReald(answer[2]), CImagd(answer[2]),
                CReald(answer[3]), CImagd(answer[3]) );
    }

    printf( "test_calcEJones_analytic() passed %d/%d tests\n", npassed, ntests );
}