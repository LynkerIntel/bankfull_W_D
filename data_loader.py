# Libraries
from sklearn.preprocessing import PowerTransformer, QuantileTransformer, StandardScaler, RobustScaler, MinMaxScaler, MaxAbsScaler, FunctionTransformer
import scipy
import matplotlib.pyplot as plt
from matplotlib import pyplot
import pandas as pd
import numpy as np
import pickle
import os
import json

# FHG dataset
# --------------------------- Read data files --------------------------- #
class DataLoader:
    """ Main body of the data loader for preparing data for ML models

    Parameters
    ----------
    data_path : str
        The path to data that is used in ML model
    target_data_path : str
        The path to target widt/depth data that is used in ML model
    rand_state : int
        A random state number
    out_feature : str
        The name of the FHG coeficent to be used
    custom_name : str
        A custom name defiend by user to name modeling task
    x_transform : str
        Whether to apply transformation to predictor variables or not 
        Opptions are:
        - True
        - False
    x_transform : str
        Whether to apply transformation to predictor variables or not 
        Opptions are:
        - True
        - False
        - defaults to False
    y_transform : bool
        Whether to apply transformation to target variable or not 
        Opptions are:
        - True
        - False
        - defaults to False
    R2_thresh : float
        The desired coeficent of determation to filter out bad measurments
        Opptions are:
        - any value between 0.0 - 100.0
        - defaults to 0.0
    Example
    --------
    >>> DataLoader(data_path = 'data/test.parquet', out_feature = 'b', rand_state = 115,
        custom_name = 'test', x_transform = False, y_transform = False, R2_thresh = 0.0)
        
    """
    def __init__(self, data_path: str, target_data_path: str, rand_state: int, out_feature: str, 
                 custom_name: str, x_transform: bool = False, 
                 y_transform: bool = False, R2_thresh: float = 0.0) -> None:
        pd.options.display.max_columns  = 60
        self.data_path                  = data_path
        self.target_data_path           = target_data_path
        self.data                       = pd.DataFrame([])
        self.data_target                       = pd.DataFrame([])
        self.rand_state                 = rand_state
        np.random.seed(self.rand_state)
        self.in_features                = []
        self.out_feature                = out_feature
        self.custom_name                = custom_name
        self.x_transform                = x_transform
        self.y_transform                = y_transform
        self.train                      = pd.DataFrame([])
        self.test                       = pd.DataFrame([])
        self.R2_thresh                  = R2_thresh

        # ___________________________________________________
        # Check directories
        if not os.path.isdir(os.path.join(os.getcwd(),self.custom_name,"model/")):
            os.mkdir(os.path.join(os.getcwd(),self.custom_name,"model/"))

    def readFiles(self) -> None:
        """ Read files from the directories
        """
        try:
            self.data = pd.read_parquet(self.data_path, engine='pyarrow')
            self.data.astype({'siteID': 'string'})
            self.data_target = pd.read_parquet(self.target_data_path, engine='pyarrow')
            self.data_target.astype({'siteID': 'string'})
        except:
            print('Wrong address or data format. Please use parquet file.')   
        
        # ___________________________________________________
        # Merge data and prepare targets
        self.data_target = self.data_target[set(self.data_target) - set(['lat','long','meas_q_va','stream_wdth_va','max_depth_va'])]
        self.data = pd.merge(self.data_target, self.data, on='siteID', how = 'inner')

        # ___________________________________________________
        # Filter bad stations
        target_df = pd.read_parquet(self.target_data_path, engine='pyarrow')
        target_df.astype({'siteID': 'string'})
        
        r2_epochs = np.arange(0, 1.05, 0.05)
        grouped_r2 = target_df.groupby('siteID').agg('mean')
        count_list = [len(grouped_r2)]
        for epoch in r2_epochs:
            count_Y = len(grouped_r2.loc[grouped_r2['R2']>=epoch])
            count_list.append(count_Y)

        r2_epochs = np.insert(r2_epochs, 0, -0.05, axis=0)
        fig, ax = plt.subplots(1, 1, figsize=(6,6))
        scale = 30
        ax.grid(True)
        ax.scatter(np.array(count_list)/len(grouped_r2), r2_epochs, c='r', s=scale, label='Y',
                    alpha=0.6, edgecolors='k')
    
        plt.vlines(x=self.R2_thresh, ymin=0, ymax=1, colors='purple', ls='--', lw=2, label='Threshold')
        ax.legend()
        ax.set_ylim([0, 1])
        plt.xlabel("R2")
        plt.ylabel("% stations greater than or equal")
        my_plot = plt.gcf()
        plt.savefig(self.custom_name+'/img/model/'+str(self.custom_name)+'_'+str(self.out_feature)+'_R2_cut.png',bbox_inches='tight', dpi = 600, facecolor='white')
        plt.show()

        good_stations = grouped_r2.loc[(grouped_r2['R2'] >= self.R2_thresh)]
        good_stations = good_stations.reset_index()
        good_stations.astype({'siteID': 'string'})
        stations = good_stations['siteID'].tolist()
        del good_stations
        self.data = self.data[self.data['siteID'].isin(stations)].reset_index(drop=True)
        
        return 
        
 # --------------------------- Split train and test --------------------------- #
    
    def splitData(self, sample_type: str) -> None:
        """ 
        To split data to train and test, and whether to use all 
        features or few 

        Parameters:
        ----------
        sample_type: str
            For limiting feature space
            Options are:
            - ``All``
            - ``Sub``
            - ``test`
        Example
            --------
            >>> splitData("All")
        """
        if sample_type == "All":
            temp = json.load(open('data/model_feature_names.json'))
            model_features = [self.out_feature]+temp.get('in_features')+temp.get('id_features')#+temp.get('in_features_NWM')+temp.get('in_features_flow_freq')
            # ___________________________________________________
            # to dump variables
            # dump_list = ["BFICat","CatAreaSqKm","ElevCat","PctWaterCat","PrecipCat",
            # "RckDepCat","RockNCat","RunoffCat","WaterInputCat","WetIndexCat","WtDepCat",
            # "scat_nlcd_feature1","scat_nlcd_feature2","scat_nlcd_feature3",
            # "scat_ant_feature1","scat_ant_feature2","scat_ant_feature3",
            # "scat_lith_feature1","scat_lith_feature2","scat_lith_feature3",
            # "scat_hydra_feature1","scat_hydra_feature2","SM_ave","SM_max","SM_min","Q_mean","Qb_mean",
            # "Q_max","Qb_max","Q_min","Qb_min","ST_ave","ST_max","ST_min","ET_ave","AI","LAI_max","LAI_min",
            # "LAI_ave","Precip_ave","Precip_max","Precip_min","NDVI_max","NDVI_min","NDVI_ave","aspect_ave",
            # "slope_ave","elevation_ave"]
            # model_features = list(set(model_features) - set(dump_list))
            self.in_features = model_features.copy()
            self.in_features = list(set(self.in_features) - set(temp.get('id_features')) - set([self.out_feature]))
        else:
            temp = json.load(open('model_space/feature_space.json'))
            temp = temp.get(sample_type).get(self.out_feature+'_feats')
            model_features = temp
            self.in_features = model_features.copy()
            temp = json.load(open('data/model_feature_names.json'))
            model_features += temp.get('out_features')+temp.get('id_features')

        del temp
        
        # Apply some filtering
        if "TW_" in self.out_feature: 
            # The widest navigable section in the shipping channel of the Mississippi is Lake Pepin, where the channel is approximately 2 miles wide
            # here we consider 3 miles or 15840 ft
            self.data = self.data.loc[self.data[str(self.out_feature )] < 15840]
        else:
            # The deepest river in the U.S. is the Hudson River which reaches a maximum depth of 216 ft.
            self.data = self.data.loc[self.data[str(self.out_feature )] < 216] 
        
        df_mask = self.data[model_features]
        df_mask.to_parquet(self.custom_name+'/metrics/df_mask.parquet')
        df_mask = df_mask.fillna(0) # // to be changed (compensating for EE features in cities that can be set to 0)
        msk = np.random.rand(len(df_mask)) < 0.85
        self.train = df_mask[msk]
        self.train = self.train.reset_index(drop=True)
        self.test = df_mask[~msk]
        self.test = self.test.reset_index(drop=True)
        return

# --------------------------- Transformation --------------------------- #

    def transformData(self, type: str = 'power') -> tuple[pd.DataFrame,
                                                          np.array,
                                                          pd.DataFrame,
                                                          pd.DataFrame,
                                                          np.array,
                                                          pd.DataFrame]:
        """ 
        To split data to train and test, and whether to use all 
        features or few 

        Parameters:
        ----------
        type: str
            Type of transformation
            Options are:
            - ``power`` for power transformation
            - ``any``   for quantile transformation
        
        Returns:
        ----------
        train_x: pd.DataFrame
            A dataframe containg predictor data for training 
        train_y: np.array
            An array containg target data for training 
        train_id: pd.DataFrame
            A dataframe containg site id and nwis_25 of the stations for training 
        test_x: pd.DataFrame
            A dataframe containg predictor data for testing 
        test_y: np.array
            An array containg target data for testing 
        test_id: pd.DataFrame
            A dataframe containg site id and nwis_25 of the stations for testing 

        Example
            --------
            >>> train_x, train_y, train_id, test_x, test_y, test_id = transformData("power")
        """
        dump_list = ['R2', 'siteID']
        if self.x_transform:
            if type=='power':
                # t_x = MinMaxScaler(feature_range=(0, 1))
                t_x = PowerTransformer()
            else:
                t_x = QuantileTransformer(
                    n_quantiles=500, output_distribution="normal", 
                    random_state=self.rand_state
                )
            # scaler_x = StandardScaler()
            train_x = self.train[self.in_features].reset_index(drop=True)
            train_x_t = t_x.fit_transform(train_x)
            pickle.dump(t_x, open(self.custom_name+'/model/'+'train_x_'+self.out_feature+'_tansformation.pkl', "wb"))
            # train_x_pt = scaler_x.fit_transform(train_x_pt)
            train_x = pd.DataFrame(data=train_x_t,
                    columns=train_x.columns)
            train_id =  self.train[dump_list].reset_index(drop=True)

            test_x = self.test[self.in_features].reset_index(drop=True)
            test_x_t = t_x.transform(test_x)
            # test_x_pt = scaler_x.transform(test_x_pt)
            test_x = pd.DataFrame(data=test_x_t,
                    columns=test_x.columns)
            test_id =  self.test[dump_list].reset_index(drop=True)

        else:
            train_x = self.train[self.in_features].reset_index(drop=True)
            train_id =  self.train[dump_list].reset_index(drop=True)
            test_x = self.test[self.in_features].reset_index(drop=True)
            test_id =  self.test[dump_list].reset_index(drop=True)

        if self.y_transform:
            if type=='power':
                # t_y = MinMaxScaler(feature_range=(0, 1))
                t_y = PowerTransformer()
            else:    
                t_y = QuantileTransformer(
                    n_quantiles=500, output_distribution="normal", 
                    random_state=self.rand_state
                )
            # scaler_y = StandardScaler()
            train_y = self.train[[self.out_feature]].reset_index(drop=True)
            train_y_t = t_y.fit_transform(train_y)
            pickle.dump(t_y, open(self.custom_name+'/model/'+'train_y_'+self.out_feature+'_tansformation.pkl', "wb"))
            # train_y_pt = scaler_x.fit_transform(train_y_pt)
            train_y = train_y_t.ravel()

            test_y = self.test[[self.out_feature]].reset_index(drop=True)
            test_y_t = t_y.transform(test_y)
            # test_y_pt = scaler_y.transform(test_y_pt)
            test_y = test_y_t.ravel()
        else:
            train_y = self.train[[self.out_feature]].reset_index(drop=True)
            train_y = train_y.values.ravel()
            test_y = self.test[[self.out_feature]].reset_index(drop=True)
            test_y = test_y.to_numpy().reshape((-1,))
        
        return train_x, train_y, train_id, test_x, test_y, test_id
