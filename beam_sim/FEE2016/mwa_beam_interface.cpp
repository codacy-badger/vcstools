// TEST PROGRAM FOR beam model 2016 :

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define GRIDPOINTS_COUNT 197

#ifdef _MWA_2016_BEAM_MODEL_
#include "beam2016implementation.h"
#else
   #define N_ANT_COUNT 16
#endif 

extern int gPrintfLevel;

struct cGridPoint
{
   int gridpoint;
   double azim;
   double elev;
   double delays[N_ANT_COUNT];
};


cGridPoint* find_closest_gridpoint( double az_deg, double za_deg );
cGridPoint* get_gridpoint( int gridpoint );

double CalcMWABeam( double az, double za, double freq_hz, char beam, int gridpoint, int zenith_norm )
{
   const double default_delays[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
   const double default_amps[16]   = {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1};
   
   const double* delays = default_delays;
   const double* amps   = default_amps;
   if( gridpoint>=0 && gridpoint<GRIDPOINTS_COUNT ){
      cGridPoint* pGridPoint = get_gridpoint( gridpoint );
      if( !pGridPoint ){
         printf("ERROR : could not find sweet spot for pointing at (az,za) = (%.4f,%.4f) [deg]\n",az,za);
         exit(-1);         
      }
      
      delays = pGridPoint->delays;
      if( gPrintfLevel >= 5 ){
         printf("Found optimal gridpoint = %d at (az,elev) = (%.4f,%.4f) [deg]\n",pGridPoint->gridpoint,pGridPoint->azim,pGridPoint->elev);
      }
   }else{
      printf("ERROR : wrong gridpoint = %d -> exiting now !\n",gridpoint);
      exit(-1);
   }
   
   double beam_out = 0.00;
#ifdef _MWA_2016_BEAM_MODEL_
   static Beam2016Implementation fullee(delays, amps);   
   JonesMatrix jones_matrix = fullee.CalcJones( az, za, freq_hz, zenith_norm );

   if( gPrintfLevel >= 5 ){
      printf("Jones = \n");
      printf("---------------------------------------------------\n");
      printf("\t%.8f + %.8fj     |     %.8f + %.8fj\n",jones_matrix.j00.real(),jones_matrix.j00.imag(),jones_matrix.j01.real(),jones_matrix.j01.imag());
      printf("\t%.8f + %.8fj     |     %.8f + %.8fj\n",jones_matrix.j10.real(),jones_matrix.j10.imag(),jones_matrix.j11.real(),jones_matrix.j11.imag());
      printf("---------------------------------------------------\n");
   }

   // calculate XX or YY beams as in :
   // mwa_tile.py / makeUnpolInstrumentalResponse 
   // see also primary_beam.py MWA_Tile_full_EE :
   // vis = mwa_tile.makeUnpolInstrumentalResponse(j,j)
   // if not power:
   //    return (numpy.sqrt(vis[:,:,0,0].real),numpy.sqrt(vis[:,:,1,1].real))
   // else:
   //    return (vis[:,:,0,0].real,vis[:,:,1,1].real)                           
   
   // POWER BEAMS (SQR of beams X and Y):
   double beam_xx = std::abs( jones_matrix.j00 )*std::abs( jones_matrix.j00 ) + std::abs( jones_matrix.j01 )*std::abs( jones_matrix.j01 ); 
   double beam_yy = std::abs( jones_matrix.j10 )*std::abs( jones_matrix.j10 ) + std::abs( jones_matrix.j11 )*std::abs( jones_matrix.j11 );
   
   beam_out = beam_xx + beam_yy; 
   // double beam_out = sqrt( beam_xx + beam_yy );
#else
   printf("ERROR : MWA 2016 beam model not implemented in this version, use -D_MWA_2016_BEAM_MODEL_ in the compilation process\n");
   exit(-1);   
#endif
   
   return beam_out;
}



// double CalcMWABeam( double az, double za, double freq_hz, char beam='X', int zenith_norm=0, int find_closest=1, int speed_test =1 )
double CalcMWABeam_FindClosest( double az, double za, double freq_hz, char beam, int zenith_norm, int find_closest, int speed_test )
{
   const double default_delays[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
   const double default_amps[16]   = {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1};
   
   const double* delays = default_delays; // CBeamModel_FullEE::m_DefaultDelays; // {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
   const double* amps   = default_amps;   // CBeamModel_FullEE::m_DefaultAmps;   // {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1};
   if( find_closest ){
      cGridPoint* pGridPoint = find_closest_gridpoint( az, za );
      if( !pGridPoint ){
         printf("ERROR : could not find sweet spot for pointing at (az,za) = (%.4f,%.4f) [deg]\n",az,za);
         exit(-1);         
      }
      
      printf("Found optimal gridpoint = %d at (az,elev) = (%.4f,%.4f) [deg]\n",pGridPoint->gridpoint,pGridPoint->azim,pGridPoint->elev);
      
      delays = pGridPoint->delays;
   }
   
   double beam_out = 0.00;
#ifdef _MWA_2016_BEAM_MODEL_
   static Beam2016Implementation fullee(delays, amps);   
   JonesMatrix jones_matrix = fullee.CalcJones( az, za, freq_hz, zenith_norm );

   if( gPrintfLevel >= 5 ){
      printf("Jones = \n");
      printf("---------------------------------------------------\n");
      printf("\t%.8f + %.8fj     |     %.8f + %.8fj\n",jones_matrix.j00.real(),jones_matrix.j00.imag(),jones_matrix.j01.real(),jones_matrix.j01.imag());
      printf("\t%.8f + %.8fj     |     %.8f + %.8fj\n",jones_matrix.j10.real(),jones_matrix.j10.imag(),jones_matrix.j11.real(),jones_matrix.j11.imag());
      printf("---------------------------------------------------\n");
   }

/*   if( beam == 'X' ){
      beam_out = std::abs( jones_matrix.j00 )*std::abs( jones_matrix.j00 ); 
   }
   if( beam == 'Y' ){
      beam_out = std::abs( jones_matrix.j11 )*std::abs( jones_matrix.j11 );
   }*/
   // POWER BEAMS (SQR of beams X and Y):
   double beam_xx = std::abs( jones_matrix.j00 )*std::abs( jones_matrix.j00 ) + std::abs( jones_matrix.j01 )*std::abs( jones_matrix.j01 );
   double beam_yy = std::abs( jones_matrix.j10 )*std::abs( jones_matrix.j10 ) + std::abs( jones_matrix.j11 )*std::abs( jones_matrix.j11 );
               
   beam_out = beam_xx + beam_yy ; // add sqrt or not 
                  
#else
   printf("ERROR : MWA 2016 beam model not implemented in this version, use -D_MWA_2016_BEAM_MODEL_ in the compilation process\n");
   exit(-1);   
#endif
   
   return beam_out;
}



// name  , number , azimuth  , elevation ,        za        ,                     delays  
cGridPoint all_grid_points[] = {
 // number , azimuth , elevation , delays 
 { 0 , 0 , 90 , {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0} },
 { 1 , 0 , 83.1912 , {3,3,3,3,2,2,2,2,1,1,1,1,0,0,0,0} },
 { 2 , 90 , 83.1912 , {0,1,2,3,0,1,2,3,0,1,2,3,0,1,2,3} },
 { 3 , 180 , 83.1912 , {0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3} },
 { 4 , 270 , 83.1912 , {3,2,1,0,3,2,1,0,3,2,1,0,3,2,1,0} },
 { 5 , 45 , 80.348 , {3,4,5,6,2,3,4,5,1,2,3,4,0,1,2,3} },
 { 6 , 135 , 80.348 , {0,1,2,3,1,2,3,4,2,3,4,5,3,4,5,6} },
 { 7 , 225 , 80.348 , {3,2,1,0,4,3,2,1,5,4,3,2,6,5,4,3} },
 { 8 , 315 , 80.348 , {6,5,4,3,5,4,3,2,4,3,2,1,3,2,1,0} },
 { 9 , 0 , 76.2838 , {6,6,6,6,4,4,4,4,2,2,2,2,0,0,0,0} },
 { 10 , 90 , 76.2838 , {0,2,4,6,0,2,4,6,0,2,4,6,0,2,4,6} },
 { 11 , 180 , 76.2838 , {0,0,0,0,2,2,2,2,4,4,4,4,6,6,6,6} },
 { 12 , 270 , 76.2838 , {6,4,2,0,6,4,2,0,6,4,2,0,6,4,2,0} },
 { 13 , 26.5651 , 74.6271 , {6,7,8,9,4,5,6,7,2,3,4,5,0,1,2,3} },
 { 14 , 63.4349 , 74.6271 , {3,5,7,9,2,4,6,8,1,3,5,7,0,2,4,6} },
 { 15 , 116.5651 , 74.6271 , {0,2,4,6,1,3,5,7,2,4,6,8,3,5,7,9} },
 { 16 , 153.4349 , 74.6271 , {0,1,2,3,2,3,4,5,4,5,6,7,6,7,8,9} },
 { 17 , 206.5651 , 74.6271 , {3,2,1,0,5,4,3,2,7,6,5,4,9,8,7,6} },
 { 18 , 243.4349 , 74.6271 , {6,4,2,0,7,5,3,1,8,6,4,2,9,7,5,3} },
 { 19 , 296.5651 , 74.6271 , {9,7,5,3,8,6,4,2,7,5,3,1,6,4,2,0} },
 { 20 , 333.4349 , 74.6271 , {9,8,7,6,7,6,5,4,5,4,3,2,3,2,1,0} },
 { 21 , 45 , 70.4075 , {6,8,10,12,4,6,8,10,2,4,6,8,0,2,4,6} },
 { 22 , 135 , 70.4075 , {0,2,4,6,2,4,6,8,4,6,8,10,6,8,10,12} },
 { 23 , 225 , 70.4075 , {6,4,2,0,8,6,4,2,10,8,6,4,12,10,8,6} },
 { 24 , 315 , 70.4075 , {12,10,8,6,10,8,6,4,8,6,4,2,6,4,2,0} },
 { 25 , 0 , 69.1655 , {9,9,9,9,6,6,6,6,3,3,3,3,0,0,0,0} },
 { 26 , 90 , 69.1655 , {0,3,6,9,0,3,6,9,0,3,6,9,0,3,6,9} },
 { 27 , 180 , 69.1655 , {0,0,0,0,3,3,3,3,6,6,6,6,9,9,9,9} },
 { 28 , 270 , 69.1655 , {9,6,3,0,9,6,3,0,9,6,3,0,9,6,3,0} },
 { 29 , 18.4349 , 67.9813 , {9,10,11,12,6,7,8,9,3,4,5,6,0,1,2,3} },
 { 30 , 71.5651 , 67.9813 , {3,6,9,12,2,5,8,11,1,4,7,10,0,3,6,9} },
 { 31 , 108.4349 , 67.9813 , {0,3,6,9,1,4,7,10,2,5,8,11,3,6,9,12} },
 { 32 , 161.5651 , 67.9813 , {0,1,2,3,3,4,5,6,6,7,8,9,9,10,11,12} },
 { 33 , 198.4349 , 67.9813 , {3,2,1,0,6,5,4,3,9,8,7,6,12,11,10,9} },
 { 34 , 251.5651 , 67.9813 , {9,6,3,0,10,7,4,1,11,8,5,2,12,9,6,3} },
 { 35 , 288.4349 , 67.9813 , {12,9,6,3,11,8,5,2,10,7,4,1,9,6,3,0} },
 { 36 , 341.5651 , 67.9813 , {12,11,10,9,9,8,7,6,6,5,4,3,3,2,1,0} },
 { 37 , 33.6901 , 64.6934 , {9,11,13,15,6,8,10,12,3,5,7,9,0,2,4,6} },
 { 38 , 56.3099 , 64.6934 , {6,9,12,15,4,7,10,13,2,5,8,11,0,3,6,9} },
 { 39 , 123.6901 , 64.6934 , {0,3,6,9,2,5,8,11,4,7,10,13,6,9,12,15} },
 { 40 , 146.3099 , 64.6934 , {0,2,4,6,3,5,7,9,6,8,10,12,9,11,13,15} },
 { 41 , 213.6901 , 64.6934 , {6,4,2,0,9,7,5,3,12,10,8,6,15,13,11,9} },
 { 42 , 236.3099 , 64.6934 , {9,6,3,0,11,8,5,2,13,10,7,4,15,12,9,6} },
 { 43 , 303.6901 , 64.6934 , {15,12,9,6,13,10,7,4,11,8,5,2,9,6,3,0} },
 { 44 , 326.3099 , 64.6934 , {15,13,11,9,12,10,8,6,9,7,5,3,6,4,2,0} },
 { 45 , 0 , 61.691 , {12,12,12,12,8,8,8,8,4,4,4,4,0,0,0,0} },
 { 46 , 90 , 61.691 , {0,4,8,12,0,4,8,12,0,4,8,12,0,4,8,12} },
 { 47 , 180 , 61.691 , {0,0,0,0,4,4,4,4,8,8,8,8,12,12,12,12} },
 { 48 , 270 , 61.691 , {12,8,4,0,12,8,4,0,12,8,4,0,12,8,4,0} },
 { 49 , 14.0362 , 60.7369 , {12,13,14,15,8,9,10,11,4,5,6,7,0,1,2,3} },
 { 50 , 75.9638 , 60.7369 , {3,7,11,15,2,6,10,14,1,5,9,13,0,4,8,12} },
 { 51 , 104.0362 , 60.7369 , {0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15} },
 { 52 , 165.9638 , 60.7369 , {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15} },
 { 53 , 194.0362 , 60.7369 , {3,2,1,0,7,6,5,4,11,10,9,8,15,14,13,12} },
 { 54 , 255.9638 , 60.7369 , {12,8,4,0,13,9,5,1,14,10,6,2,15,11,7,3} },
 { 55 , 284.0362 , 60.7369 , {15,11,7,3,14,10,6,2,13,9,5,1,12,8,4,0} },
 { 56 , 345.9638 , 60.7369 , {15,14,13,12,11,10,9,8,7,6,5,4,3,2,1,0} },
 { 57 , 45 , 59.8018 , {9,12,15,18,6,9,12,15,3,6,9,12,0,3,6,9} },
 { 58 , 135 , 59.8018 , {0,3,6,9,3,6,9,12,6,9,12,15,9,12,15,18} },
 { 59 , 225 , 59.8018 , {9,6,3,0,12,9,6,3,15,12,9,6,18,15,12,9} },
 { 60 , 315 , 59.8018 , {18,15,12,9,15,12,9,6,12,9,6,3,9,6,3,0} },
 { 61 , 26.5651 , 57.981 , {12,14,16,18,8,10,12,14,4,6,8,10,0,2,4,6} },
 { 62 , 63.4349 , 57.981 , {6,10,14,18,4,8,12,16,2,6,10,14,0,4,8,12} },
 { 63 , 116.5651 , 57.981 , {0,4,8,12,2,6,10,14,4,8,12,16,6,10,14,18} },
 { 64 , 153.4349 , 57.981 , {0,2,4,6,4,6,8,10,8,10,12,14,12,14,16,18} },
 { 65 , 206.5651 , 57.981 , {6,4,2,0,10,8,6,4,14,12,10,8,18,16,14,12} },
 { 66 , 243.4349 , 57.981 , {12,8,4,0,14,10,6,2,16,12,8,4,18,14,10,6} },
 { 67 , 296.5651 , 57.981 , {18,14,10,6,16,12,8,4,14,10,6,2,12,8,4,0} },
 { 68 , 333.4349 , 57.981 , {18,16,14,12,14,12,10,8,10,8,6,4,6,4,2,0} },
 { 69 , 0 , 53.6453 , {15,15,15,15,10,10,10,10,5,5,5,5,0,0,0,0} },
 { 70 , 36.8699 , 53.6453 , {12,15,18,21,8,11,14,17,4,7,10,13,0,3,6,9} },
 { 71 , 53.1301 , 53.6453 , {9,13,17,21,6,10,14,18,3,7,11,15,0,4,8,12} },
 { 72 , 90 , 53.6453 , {0,5,10,15,0,5,10,15,0,5,10,15,0,5,10,15} },
 { 73 , 126.8699 , 53.6453 , {0,4,8,12,3,7,11,15,6,10,14,18,9,13,17,21} },
 { 74 , 143.1301 , 53.6453 , {0,3,6,9,4,7,10,13,8,11,14,17,12,15,18,21} },
 { 75 , 180 , 53.6453 , {0,0,0,0,5,5,5,5,10,10,10,10,15,15,15,15} },
 { 76 , 216.8699 , 53.6453 , {9,6,3,0,13,10,7,4,17,14,11,8,21,18,15,12} },
 { 77 , 233.1301 , 53.6453 , {12,8,4,0,15,11,7,3,18,14,10,6,21,17,13,9} },
 { 78 , 270 , 53.6453 , {15,10,5,0,15,10,5,0,15,10,5,0,15,10,5,0} },
 { 79 , 306.8699 , 53.6453 , {21,17,13,9,18,14,10,6,15,11,7,3,12,8,4,0} },
 { 80 , 323.1301 , 53.6453 , {21,18,15,12,17,14,11,8,13,10,7,4,9,6,3,0} },
 { 81 , 11.3099 , 52.8056 , {15,16,17,18,10,11,12,13,5,6,7,8,0,1,2,3} },
 { 82 , 78.6901 , 52.8056 , {3,8,13,18,2,7,12,17,1,6,11,16,0,5,10,15} },
 { 83 , 101.3099 , 52.8056 , {0,5,10,15,1,6,11,16,2,7,12,17,3,8,13,18} },
 { 84 , 168.6901 , 52.8056 , {0,1,2,3,5,6,7,8,10,11,12,13,15,16,17,18} },
 { 85 , 191.3099 , 52.8056 , {3,2,1,0,8,7,6,5,13,12,11,10,18,17,16,15} },
 { 86 , 258.6901 , 52.8056 , {15,10,5,0,16,11,6,1,17,12,7,2,18,13,8,3} },
 { 87 , 281.3099 , 52.8056 , {18,13,8,3,17,12,7,2,16,11,6,1,15,10,5,0} },
 { 88 , 348.6901 , 52.8056 , {18,17,16,15,13,12,11,10,8,7,6,5,3,2,1,0} },
 { 89 , 21.8014 , 50.3239 , {15,17,19,21,10,12,14,16,5,7,9,11,0,2,4,6} },
 { 90 , 68.1986 , 50.3239 , {6,11,16,21,4,9,14,19,2,7,12,17,0,5,10,15} },
 { 91 , 111.8014 , 50.3239 , {0,5,10,15,2,7,12,17,4,9,14,19,6,11,16,21} },
 { 92 , 158.1986 , 50.3239 , {0,2,4,6,5,7,9,11,10,12,14,16,15,17,19,21} },
 { 93 , 201.8014 , 50.3239 , {6,4,2,0,11,9,7,5,16,14,12,10,21,19,17,15} },
 { 94 , 248.1986 , 50.3239 , {15,10,5,0,17,12,7,2,19,14,9,4,21,16,11,6} },
 { 95 , 291.8014 , 50.3239 , {21,16,11,6,19,14,9,4,17,12,7,2,15,10,5,0} },
 { 96 , 338.1986 , 50.3239 , {21,19,17,15,16,14,12,10,11,9,7,5,6,4,2,0} },
 { 97 , 45 , 47.8822 , {12,16,20,24,8,12,16,20,4,8,12,16,0,4,8,12} },
 { 98 , 135 , 47.8822 , {0,4,8,12,4,8,12,16,8,12,16,20,12,16,20,24} },
 { 99 , 225 , 47.8822 , {12,8,4,0,16,12,8,4,20,16,12,8,24,20,16,12} },
 { 100 , 315 , 47.8822 , {24,20,16,12,20,16,12,8,16,12,8,4,12,8,4,0} },
 { 101 , 30.9638 , 46.2671 , {15,18,21,24,10,13,16,19,5,8,11,14,0,3,6,9} },
 { 102 , 59.0362 , 46.2671 , {9,14,19,24,6,11,16,21,3,8,13,18,0,5,10,15} },
 { 103 , 120.9638 , 46.2671 , {0,5,10,15,3,8,13,18,6,11,16,21,9,14,19,24} },
 { 104 , 149.0362 , 46.2671 , {0,3,6,9,5,8,11,14,10,13,16,19,15,18,21,24} },
 { 105 , 210.9638 , 46.2671 , {9,6,3,0,14,11,8,5,19,16,13,10,24,21,18,15} },
 { 106 , 239.0362 , 46.2671 , {15,10,5,0,18,13,8,3,21,16,11,6,24,19,14,9} },
 { 107 , 300.9638 , 46.2671 , {24,19,14,9,21,16,11,6,18,13,8,3,15,10,5,0} },
 { 108 , 329.0362 , 46.2671 , {24,21,18,15,19,16,13,10,14,11,8,5,9,6,3,0} },
 { 109 , 0 , 44.656 , {18,18,18,18,12,12,12,12,6,6,6,6,0,0,0,0} },
 { 110 , 90 , 44.656 , {0,6,12,18,0,6,12,18,0,6,12,18,0,6,12,18} },
 { 111 , 180 , 44.656 , {0,0,0,0,6,6,6,6,12,12,12,12,18,18,18,18} },
 { 112 , 270 , 44.656 , {18,12,6,0,18,12,6,0,18,12,6,0,18,12,6,0} },
 { 113 , 9.4623 , 43.8504 , {18,19,20,21,12,13,14,15,6,7,8,9,0,1,2,3} },
 { 114 , 80.5377 , 43.8504 , {3,9,15,21,2,8,14,20,1,7,13,19,0,6,12,18} },
 { 115 , 99.4623 , 43.8504 , {0,6,12,18,1,7,13,19,2,8,14,20,3,9,15,21} },
 { 116 , 170.5377 , 43.8504 , {0,1,2,3,6,7,8,9,12,13,14,15,18,19,20,21} },
 { 117 , 189.4623 , 43.8504 , {3,2,1,0,9,8,7,6,15,14,13,12,21,20,19,18} },
 { 118 , 260.5377 , 43.8504 , {18,12,6,0,19,13,7,1,20,14,8,2,21,15,9,3} },
 { 119 , 279.4623 , 43.8504 , {21,15,9,3,20,14,8,2,19,13,7,1,18,12,6,0} },
 { 120 , 350.5377 , 43.8504 , {21,20,19,18,15,14,13,12,9,8,7,6,3,2,1,0} },
 { 121 , 18.4349 , 41.4255 , {18,20,22,24,12,14,16,18,6,8,10,12,0,2,4,6} },
 { 122 , 71.5651 , 41.4255 , {6,12,18,24,4,10,16,22,2,8,14,20,0,6,12,18} },
 { 123 , 108.4349 , 41.4255 , {0,6,12,18,2,8,14,20,4,10,16,22,6,12,18,24} },
 { 124 , 161.5651 , 41.4255 , {0,2,4,6,6,8,10,12,12,14,16,18,18,20,22,24} },
 { 125 , 198.4349 , 41.4255 , {6,4,2,0,12,10,8,6,18,16,14,12,24,22,20,18} },
 { 126 , 251.5651 , 41.4255 , {18,12,6,0,20,14,8,2,22,16,10,4,24,18,12,6} },
 { 127 , 288.4349 , 41.4255 , {24,18,12,6,22,16,10,4,20,14,8,2,18,12,6,0} },
 { 128 , 341.5651 , 41.4255 , {24,22,20,18,18,16,14,12,12,10,8,6,6,4,2,0} },
 { 129 , 38.6598 , 40.6123 , {15,19,23,27,10,14,18,22,5,9,13,17,0,4,8,12} },
 { 130 , 51.3402 , 40.6123 , {12,17,22,27,8,13,18,23,4,9,14,19,0,5,10,15} },
 { 131 , 128.6598 , 40.6123 , {0,5,10,15,4,9,14,19,8,13,18,23,12,17,22,27} },
 { 132 , 141.3402 , 40.6123 , {0,4,8,12,5,9,13,17,10,14,18,22,15,19,23,27} },
 { 133 , 218.6598 , 40.6123 , {12,8,4,0,17,13,9,5,22,18,14,10,27,23,19,15} },
 { 134 , 231.3402 , 40.6123 , {15,10,5,0,19,14,9,4,23,18,13,8,27,22,17,12} },
 { 135 , 308.6598 , 40.6123 , {27,22,17,12,23,18,13,8,19,14,9,4,15,10,5,0} },
 { 136 , 321.3402 , 40.6123 , {27,23,19,15,22,18,14,10,17,13,9,5,12,8,4,0} },
 { 137 , 26.5651 , 37.3163 , {18,21,24,27,12,15,18,21,6,9,12,15,0,3,6,9} },
 { 138 , 63.4349 , 37.3163 , {9,15,21,27,6,12,18,24,3,9,15,21,0,6,12,18} },
 { 139 , 116.5651 , 37.3163 , {0,6,12,18,3,9,15,21,6,12,18,24,9,15,21,27} },
 { 140 , 153.4349 , 37.3163 , {0,3,6,9,6,9,12,15,12,15,18,21,18,21,24,27} },
 { 141 , 206.5651 , 37.3163 , {9,6,3,0,15,12,9,6,21,18,15,12,27,24,21,18} },
 { 142 , 243.4349 , 37.3163 , {18,12,6,0,21,15,9,3,24,18,12,6,27,21,15,9} },
 { 143 , 296.5651 , 37.3163 , {27,21,15,9,24,18,12,6,21,15,9,3,18,12,6,0} },
 { 144 , 333.4349 , 37.3163 , {27,24,21,18,21,18,15,12,15,12,9,6,9,6,3,0} },
 { 145 , 0 , 33.912 , {21,21,21,21,14,14,14,14,7,7,7,7,0,0,0,0} },
 { 146 , 90 , 33.912 , {0,7,14,21,0,7,14,21,0,7,14,21,0,7,14,21} },
 { 147 , 180 , 33.912 , {0,0,0,0,7,7,7,7,14,14,14,14,21,21,21,21} },
 { 148 , 270 , 33.912 , {21,14,7,0,21,14,7,0,21,14,7,0,21,14,7,0} },
 { 149 , 8.1301 , 33.0368 , {21,22,23,24,14,15,16,17,7,8,9,10,0,1,2,3} },
 { 150 , 45 , 33.0368 , {15,20,25,30,10,15,20,25,5,10,15,20,0,5,10,15} },
 { 151 , 81.8699 , 33.0368 , {3,10,17,24,2,9,16,23,1,8,15,22,0,7,14,21} },
 { 152 , 98.1301 , 33.0368 , {0,7,14,21,1,8,15,22,2,9,16,23,3,10,17,24} },
 { 153 , 135 , 33.0368 , {0,5,10,15,5,10,15,20,10,15,20,25,15,20,25,30} },
 { 154 , 171.8699 , 33.0368 , {0,1,2,3,7,8,9,10,14,15,16,17,21,22,23,24} },
 { 155 , 188.1301 , 33.0368 , {3,2,1,0,10,9,8,7,17,16,15,14,24,23,22,21} },
 { 156 , 225 , 33.0368 , {15,10,5,0,20,15,10,5,25,20,15,10,30,25,20,15} },
 { 157 , 261.8699 , 33.0368 , {21,14,7,0,22,15,8,1,23,16,9,2,24,17,10,3} },
 { 158 , 278.1301 , 33.0368 , {24,17,10,3,23,16,9,2,22,15,8,1,21,14,7,0} },
 { 159 , 315 , 33.0368 , {30,25,20,15,25,20,15,10,20,15,10,5,15,10,5,0} },
 { 160 , 351.8699 , 33.0368 , {24,23,22,21,17,16,15,14,10,9,8,7,3,2,1,0} },
 { 161 , 33.6901 , 31.2488 , {18,22,26,30,12,16,20,24,6,10,14,18,0,4,8,12} },
 { 162 , 56.3099 , 31.2488 , {12,18,24,30,8,14,20,26,4,10,16,22,0,6,12,18} },
 { 163 , 123.6901 , 31.2488 , {0,6,12,18,4,10,16,22,8,14,20,26,12,18,24,30} },
 { 164 , 146.3099 , 31.2488 , {0,4,8,12,6,10,14,18,12,16,20,24,18,22,26,30} },
 { 165 , 213.6901 , 31.2488 , {12,8,4,0,18,14,10,6,24,20,16,12,30,26,22,18} },
 { 166 , 236.3099 , 31.2488 , {18,12,6,0,22,16,10,4,26,20,14,8,30,24,18,12} },
 { 167 , 303.6901 , 31.2488 , {30,24,18,12,26,20,14,8,22,16,10,4,18,12,6,0} },
 { 168 , 326.3099 , 31.2488 , {30,26,22,18,24,20,16,12,18,14,10,6,12,8,4,0} },
 { 169 , 15.9454 , 30.3331 , {21,23,25,27,14,16,18,20,7,9,11,13,0,2,4,6} },
 { 170 , 74.0546 , 30.3331 , {6,13,20,27,4,11,18,25,2,9,16,23,0,7,14,21} },
 { 171 , 105.9454 , 30.3331 , {0,7,14,21,2,9,16,23,4,11,18,25,6,13,20,27} },
 { 172 , 164.0546 , 30.3331 , {0,2,4,6,7,9,11,13,14,16,18,20,21,23,25,27} },
 { 173 , 195.9454 , 30.3331 , {6,4,2,0,13,11,9,7,20,18,16,14,27,25,23,21} },
 { 174 , 254.0546 , 30.3331 , {21,14,7,0,23,16,9,2,25,18,11,4,27,20,13,6} },
 { 175 , 285.9454 , 30.3331 , {27,20,13,6,25,18,11,4,23,16,9,2,21,14,7,0} },
 { 176 , 344.0546 , 30.3331 , {27,25,23,21,20,18,16,14,13,11,9,7,6,4,2,0} },
 { 177 , 23.1986 , 25.4582 , {21,24,27,30,14,17,20,23,7,10,13,16,0,3,6,9} },
 { 178 , 66.8014 , 25.4582 , {9,16,23,30,6,13,20,27,3,10,17,24,0,7,14,21} },
 { 179 , 113.1986 , 25.4582 , {0,7,14,21,3,10,17,24,6,13,20,27,9,16,23,30} },
 { 180 , 156.8014 , 25.4582 , {0,3,6,9,7,10,13,16,14,17,20,23,21,24,27,30} },
 { 181 , 203.1986 , 25.4582 , {9,6,3,0,16,13,10,7,23,20,17,14,30,27,24,21} },
 { 182 , 246.8014 , 25.4582 , {21,14,7,0,24,17,10,3,27,20,13,6,30,23,16,9} },
 { 183 , 293.1986 , 25.4582 , {30,23,16,9,27,20,13,6,24,17,10,3,21,14,7,0} },
 { 184 , 336.8014 , 25.4582 , {30,27,24,21,23,20,17,14,16,13,10,7,9,6,3,0} },
 { 185 , 0 , 18.4768 , {24,24,24,24,16,16,16,16,8,8,8,8,0,0,0,0} },
 { 186 , 90 , 18.4768 , {0,8,16,24,0,8,16,24,0,8,16,24,0,8,16,24} },
 { 187 , 180 , 18.4768 , {0,0,0,0,8,8,8,8,16,16,16,16,24,24,24,24} },
 { 188 , 270 , 18.4768 , {24,16,8,0,24,16,8,0,24,16,8,0,24,16,8,0} },
 { 189 , 7.125 , 17.0922 , {24,25,26,27,16,17,18,19,8,9,10,11,0,1,2,3} },
 { 190 , 82.875 , 17.0922 , {3,11,19,27,2,10,18,26,1,9,17,25,0,8,16,24} },
 { 191 , 97.125 , 17.0922 , {0,8,16,24,1,9,17,25,2,10,18,26,3,11,19,27} },
 { 192 , 172.875 , 17.0922 , {0,1,2,3,8,9,10,11,16,17,18,19,24,25,26,27} },
 { 193 , 187.125 , 17.0922 , {3,2,1,0,11,10,9,8,19,18,17,16,27,26,25,24} },
 { 194 , 262.875 , 17.0922 , {24,16,8,0,25,17,9,1,26,18,10,2,27,19,11,3} },
 { 195 , 277.125 , 17.0922 , {27,19,11,3,26,18,10,2,25,17,9,1,24,16,8,0} },
 { 196 , 352.875 , 17.0922 , {27,26,25,24,19,18,17,16,11,10,9,8,3,2,1,0} }
};


cGridPoint* find_closest_gridpoint( double az_deg, double za_deg )
{
   double elev_deg=90.00-za_deg;
   
   double deg2rad = M_PI/180.00;   
   double min_dist=1e6;
   int best_idx=-1;
   for(int i=0;i<GRIDPOINTS_COUNT;i++){ 
      cGridPoint& gridpoint = all_grid_points[i];
      
      double diff_az=gridpoint.azim-az_deg;
      double cos_value = sin(gridpoint.elev*deg2rad)*sin(elev_deg*deg2rad) + cos(gridpoint.elev*deg2rad)*cos(elev_deg*deg2rad)*cos( diff_az*deg2rad );            
      
      double dist=acos(cos_value);
      if( dist < min_dist ){
         min_dist = dist;
         best_idx = i;
      }
   }      
   
   if( best_idx >= 0 ){
      return &(all_grid_points[best_idx]);
   }
   
   return NULL;
}

cGridPoint* get_gridpoint( int gridpoint )
{
   if( gridpoint>=0 && gridpoint<GRIDPOINTS_COUNT ){
      return &(all_grid_points[gridpoint]);     
   }else{
      printf("ERROR : wrong gridpoint = %d -> exiting now !\n",gridpoint);  
      exit(-1);              
   }   
}
