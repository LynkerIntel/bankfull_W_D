# Liberaries
import matplotlib.pyplot as plt
from hydrotools.nwis_client.iv import IVDataService
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
import geopandas as gpd
from shapely.geometry import Polygon
from matplotlib import pyplot
import traceback
from tqdm import tqdm
from sklearn.ensemble import RandomForestRegressor
import glob
import os
import requests, zipfile, io
import csv
import re

class FloodFreq:
    """ 
    Calculates 1 and 2 year flood frequencies

    Paramters:
    ----------
    None

    Returns:
    ----------
    None

    """
    def __init__(self) -> None:
        # Read ADCP data
        os.chdir("../data")
        savedPath  = os.getcwd()
        self.adcp = pd.read_parquet(savedPath+'/adcp.parquet', engine='pyarrow')

    def findStations(self) -> np.array:
        """ 
        Filter adcp dataset to find valid stations for FF estimation

        Paramters:
        ----------
        None

        Returns:
        ----------
        sites: np.array
            An array containing siteIDs 

        """
        # Drop NA
        adcp_nona = self.adcp.dropna(subset=['site_no','dec_lat_va','dec_long_va','stream_wdth_va','max_depth_va', 'meas_q_va']).reset_index()
        adcp_nona = adcp_nona[['site_no','site_visit_start_dt',
                            'station_nm','dec_lat_va','dec_long_va',
                            'coord_datum_cd','meas_q_va','stream_wdth_va','max_depth_va']]

        # Convert datye
        adcp_nona['date'] =  pd.to_datetime(adcp_nona['site_visit_start_dt'], format='%Y-%m-%d')
        adcp_nona['date'] = adcp_nona['date'].dt.date
        adcp_nona['date'] =  pd.to_datetime(adcp_nona['date'], format='%Y-%m-%d')
        adcp_date = adcp_nona.copy()#loc[(adcp_nona['date']>='2010-01-01')].reset_index()
                                
        adcp_date = adcp_date[['site_no','date',
                            'station_nm','dec_lat_va','dec_long_va',
                            'meas_q_va','stream_wdth_va','max_depth_va']]
        adcp_date = adcp_date.rename(columns={'site_no': 'siteID', 'dec_lat_va': 'lat', 'dec_long_va':'long'})

        # Filter bounds to CONUS
        adcp_gdf = gpd.GeoDataFrame(
            adcp_date, geometry=gpd.points_from_xy(adcp_date.long, adcp_date["lat"]))
        lat_point_list = [22.02, 49.84, 47.75, 23.8, 22.02]
        lon_point_list = [-127.56, -128.79, -61.47, -69.64, -127.56]
        boundary_geom = Polygon(zip(lon_point_list, lat_point_list))
        adcp_gdf = adcp_gdf[adcp_gdf.geometry.within(boundary_geom)].reset_index(drop=True)

        # Aggrigate data
        agg_adcp = adcp_gdf.groupby('siteID').agg("max").reset_index()
        agg_adcp = agg_adcp[['siteID','lat','long','station_nm', 'meas_q_va','stream_wdth_va','max_depth_va']]
        sites = np.array(agg_adcp.siteID.array)
        return sites
    
    def getFloodFrequency(siteID: str) -> tuple[float, float, str, int]:
        """ 
        Calculated flood frequencies given a USGS siteID

        Paramters:
        ----------
        siteID: str


        Returns:
        ----------
        2year ff: float
            Station 2 year FF value
        1year ff: float
            Station 1 year FF value
        Unit: str
            Measurment unit
        Falg: int
            Identifies the source of the obtained data

        """
        # wrong answers hydrotools '01036390'
        siteID = str(siteID)
        # Retrieve data from a single site
        service = IVDataService(
            value_time_label="value_time",
            enable_cache=True
        )

        def seccondQuery(siteID):
            url = 'https://waterdata.usgs.gov/nwis/measurements?site_no='+siteID+'&agency_cd=USGS&format=rdb_expanded'
            response = requests.get(url, allow_redirects=True).content
            response = response.decode('utf-8')
            response = response[response.find('\nagency'):]
            fixed_str = response.replace('\t',',')
            try:
                observations_data = pd.read_csv(io.StringIO(fixed_str), sep=',', on_bad_lines='skip')
            except:
                # station not available 
                return None # None, None, None 
            observations_data.drop(index=observations_data.index[0], axis=0, inplace=True)
            observations_data = observations_data[['measurement_dt','discharge_va']].rename(columns={'measurement_dt': 'value_time', 'discharge_va': 'value'})
            observations_data['value_time']= pd.to_datetime(observations_data['value_time'])
            observations_data['value'] = observations_data['value'].astype(float)
            observations_data = observations_data.loc[observations_data['value']>= 0]
            
            return observations_data

        try:
            observations_data = service.get(
                sites=siteID,
                startDT='1920-01-01',
                endDT='2023-01-01'
                )
            observations_data['value'] = observations_data['value'].astype(float)
            observations_data = observations_data.loc[observations_data['value']>= 0]
            flag = 0
            annual_max = observations_data[['value_time','value']].dropna().resample('Y', on='value_time').max()
            if len(annual_max) == 1:
                flag = 1
                observations_data = seccondQuery(siteID)
                if observations_data is None:
                    ff1 = annual_max.loc[(annual_max['RI'] == 1)]
                    return siteID, ff1['value'].values[0], 1.5*ff1['value'].values[0], 'ft3/s', 5
        except:
            observations_data = seccondQuery(siteID)
            if observations_data is None:
                return siteID, None, None, None, 4
            flag = 1
            unit = ['ft3/s']
        # define the true objective function
        def objective(x, a, b, f):
            return (a * x) + (b * x**2) + f
        def objective2(x, a, b):
            return (a * x) + b 

        def annualMax(observations_data):
            annual_max = observations_data[['value_time','value']].dropna().resample('Y', on='value_time').max()
            annual_max = annual_max.dropna(axis='rows')
            annual_max = annual_max.reset_index(drop=True)
            annual_max['value'] = annual_max['value'].astype(float)
            annual_max['max_rank'] = annual_max['value'].rank(method='max', ascending=False)
            annual_max['RI'] = (len(annual_max))/annual_max['max_rank']
            annual_max['P'] = 1/annual_max['RI'] 
            return annual_max
        
        # return observations_data, flag
        # get data if hydrotools fail
        if len(observations_data) == 0 or flag == 1:
            observations_data = seccondQuery(siteID)
            flag = 1
            unit = ['ft3/s']
            if observations_data is None:
                return siteID, None, None, None, 4
            annual_max = annualMax(observations_data)
            
            # if it only has 2 year reccord
            if len(annual_max) == 2: 
                flag = 2 #01053680
                unit = 'ft3/s'
                def objective(x, a, b):
                    return (a * x) + b 
                popt, _ = curve_fit(objective, annual_max['RI'], annual_max['value'])
                # summarize the parameter values
                a, b = popt
                x_line = np.arange(0, 25, 1)
                y_line = objective2(x_line, a, b)
                ff = pd.DataFrame({"RI":x_line,"Q":y_line})
                ff2 = ff.loc[ff['RI'] == 2]
                ff1 = annual_max.loc[(annual_max['RI'] == 1)]
                return siteID, ff1['value'].values[0], ff2['Q'].values[0], unit, flag
            # if it only has 1 year reccord
            elif len(annual_max) < 2: 
                flag = 3  
                ff1 = annual_max.loc[(annual_max['RI'] == 1)]
                return siteID, ff1['value'].values[0], 1.5*ff1['value'].values[0], 'ft3/s', 5
        else: 
            flag = 0
            unit = observations_data['measurement_unit'].unique()
            annual_max = annualMax(observations_data)
            annual_max = annual_max.loc[annual_max['RI'] <= 3]
            # if it only has 2 year reccord
            if len(annual_max) == 2: 
                annual_max = annualMax(observations_data)
                flag = 2 #01053680
                unit = 'ft3/s'
                def objective(x, a, b):
                    return (a * x) + b 
                popt, _ = curve_fit(objective, annual_max['RI'], annual_max['value'])
                # summarize the parameter values
                a, b = popt
                x_line = np.arange(0, 25, 1)
                y_line = objective2(x_line, a, b)
                ff = pd.DataFrame({"RI":x_line,"Q":y_line})
                ff2 = ff.loc[ff['RI'] == 2]
                ff1 = annual_max.iloc[(annual_max['RI']-1).abs().argsort()[:1]]
                return siteID, ff1['value'].values[0], ff2['Q'].values[0], unit, flag
            # if it only has 1 year reccord
            elif len(annual_max) < 2: 
                flag = 3  
                return siteID, None, None, None, flag
    
        closest_lower2 = annual_max[annual_max['RI'] < 2]['RI'].max()
        # Find the closest value greater than the given value
        closest_greater2 = annual_max[annual_max['RI'] > 2]['RI'].min()
        

        if not(np.isnan(closest_lower2)) and not(np.isnan(closest_greater2)):
            filtered_df = annual_max[(annual_max['RI'] == closest_lower2) | (annual_max['RI'] == closest_greater2)]
            popt, _ = curve_fit(objective2, filtered_df['RI'], filtered_df['value'])
            a, b = popt
            x_line = np.arange(0, 25, 1)
            # calculate the output for the range
            y_line = objective2(x_line, a, b)
            # create a line plot for the mapping function
            # ax.plot(x_line, y_line, '--', color='red')
            ff = pd.DataFrame({"RI":x_line,"Q":y_line})
            # return 2 and 1 year flood frequncy 
            ff2 = ff.loc[ff['RI'] == 2]
        else:
            # return flag
            popt, _ = curve_fit(objective, annual_max['RI'], annual_max['value'])
            # summarize the parameter values
            a, b, f = popt
            # plot input vs output
            # fig, ax = plt.subplots(figsize = (9, 6))
            # ax.scatter(annual_max['RI'], annual_max['value'], alpha=0.7, edgecolors="k")
            # ax.set_xscale("log")
            # ax.set_yscale("log")
            x_line = np.arange(0, 25, 1)
            # calculate the output for the range
            y_line = objective(x_line, a, b, f)

            # create a line plot for the mapping function
            # ax.plot(x_line, y_line, '--', color='red')
            ff = pd.DataFrame({"RI":x_line,"Q":y_line})
            
            # return 2 and 1 year flood frequncy 
            ff2 = ff.loc[ff['RI'] == 2]
        #ff1 = ff.loc[ff['RI'] == 1]
        ff1 = annual_max.loc[(annual_max['RI'] == 1)]
        
        return siteID, ff1['value'].values[0], ff2['Q'].values[0], unit[0], flag

    


class GetFloodFreq: 
    @staticmethod
    def main(args):
        # Bulid an instance of flood frequency object
        FF = FloodFreq()
        target_sites = FF.findStations()

        def saveToParquet(df, iteration):
        # Save DataFrame to parquet file
            df.to_parquet(f'data/ff_out/TW_results_iteration_{iteration}.parquet')

        # Function to process a single row and return flood frequency data
        def processRow(row):
            return pd.Series(FF.getFloodFrequency(row['siteID']))
        # Initialize a counter
        row_counter = 0
        result_dfs = []

        for index, row in tqdm(target_sites.iterrows()):
            # Process the row and get flood frequency data
            # result_df = process_row(row) 
            result_dfs.append(processRow(row).values)
            
            row_counter += 1

            # Check if 100 rows have been processed
            if row_counter % 100 == 0:
                new_df = pd.DataFrame(result_dfs, columns=['siteID', 'in_ff', 'bf_ff', 'unit', 'flag'])
                saveToParquet(new_df, row_counter)

                result_dfs = []
                if os.path.exists('nwisiv_cache.sqlite'):
                    # Delete the sql file
                    os.remove('nwisiv_cache.sqlite')

        # After processing all rows, if there are remaining results, save them
        if result_dfs:
            new_df = pd.DataFrame(result_dfs, columns=['siteID', 'in_ff', 'bf_ff', 'unit', 'flag'])
            saveToParquet(new_df, row_counter)

if __name__ == "__main__":
    GetFloodFreq.main([])

