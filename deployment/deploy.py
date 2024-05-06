# Libraries 
# Catch warnings 
def warn(*args, **kwargs):
    pass
import warnings
warnings.warn = warn

from typing import Tuple
import data_loader as dataloader

import pickle
import json
import pandas as pd
import numpy as np
import os
import sys 
from tqdm import tqdm
from joblib import Parallel, delayed


# WD
# ---------------------------initialize --------------------------- #
class DPModel:
    """ Main body of the machine learning model for estimating bankfull width 
        and depth

        Parameters
        ----------
        rand_state : int
            A custom integer for randomness
    """
    def __init__(self, rand_state) -> None:
        # os.chdir(b'/home/arash.rad/river_3d/conus-fhg/')
        pd.options.display.max_columns = 30
        self.rand_state                = rand_state

# --------------------------- Load trained models  --------------------------- #    
    def loadModel(self, out_feature: str, vote_flag: bool = False, meta_flag: bool = False,
                    best_flag: bool = True, file: str = 'bf', model_type: str = 'xgb',
                    ) -> Tuple[any, list]:
        """ Load the trained transformed models

        Parameters
        ----------
        out_feature : str
            Name of the FHG coefficients
        vote_flag : bool
            Whether to use vote model 
            Options are:
            - True
            - False
        meta_flag : bool
            Whether to use meta model
            Options are:
            - True
            - False
        best_flag : bool
            Whether to use best model
            Options are:
            - True
            - False
        file : str
            Prefix of trained models
            Options are:
            - any string
        model_type: str
            The best model choices
            Options are:
            - xgb
            - lgb
        
       ` Example
        --------
        >>> DPModel.loadData(out_feature = 'Y-bf', vote_flag = False, meta_flag = False,
                    best_flag = True, file = 'bf', model_type = 'xgb')
        """
        
        # Load ML models
        if meta_flag:
            model = pickle.load(open('models/'+file+'_'+out_feature+'_final_Meta_Model.pickle.dat', "rb"))
            best_model = pickle.load(open('models/'+file+'_'+out_feature+'_'+model_type+'_final_Best_Model.pickle.dat', "rb"))
        elif vote_flag:
            model = pickle.load(open('models/'+file+'_'+out_feature+'_final_Voting_Model.pickle.dat', "rb"))
            best_model = pickle.load(open('models/'+file+'_'+out_feature+'_'+model_type+'_final_Best_Model.pickle.dat', "rb"))
        elif best_flag:
            model = best_model = pickle.load(open('models/'+file+'_'+out_feature+'_'+model_type+'_final_Best_Model.pickle.dat', "rb"))
        
        # Extract feature names
        json_trans_path = 'model_space/trans_feats'+'_'+out_feature+"_"+'.json'
        json_model_path = 'model_space/model_feats'+'_'+out_feature+'_'+'.json'

        # Read the JSON file and convert its contents into a Python list
        with open(json_trans_path, 'r') as json_file:
            trans_list = json.load(json_file)
        with open(json_model_path, 'r') as json_file:
            model_list = json.load(json_file)

        # Function to reconstruct the original list from the serialized format
        def restore_order(item):
            return item['value']

        # Reconstruct the original list while preserving the order
        trans_feats = [restore_order(item) for item in trans_list]
        model_feats = [restore_order(item) for item in model_list]
 
        return model, trans_feats, model_feats
    
    def process_target(self, dl_obj, target_name: str, vote_flag: bool=False, meta_flag: bool=False, 
                        best_flag: bool=True, file: str='bf', model_type: str='xgb') -> Tuple[str, np.array]:
        
        # dl_obj.addExtraFeatures(target_name) # already included in data
        
        if target_name == 'Y_bf':
            model_type = 'xgb'
            x_transform = False
            y_transform = False
        elif target_name == 'Y_in':
            model_type = 'xgb'
            x_transform = False
            y_transform = False
        elif target_name == 'TW_bf':
            model_type = 'xgb'
            x_transform = False
            y_transform = False
        else:
            model_type = 'xgb'
            x_transform = False
            y_transform = False

        model, trans_feats, model_feats = self.loadModel(target_name, vote_flag=False, meta_flag=False, 
                                      best_flag=True, file='NWM', model_type=model_type)

        dl_obj.transformXData(out_feature=target_name, trans_feats=trans_feats,
                                t_type='power', x_transform=x_transform)
        # has_missing_y = np.isnan(dl_obj.data).any()
        rows_with_nan = dl_obj.data[dl_obj.data.isnull().any(axis=1)]
        # if has_missing_y:
        print("Part2 Rows with NaN values:")
        print(rows_with_nan)

        data_in = dl_obj.buildPCA(target_name)

        y_pred_label = 'owp_' + target_name
        if target_name.endswith("in"):
            y_pred_label = y_pred_label+'chan'
        y_pred_label = y_pred_label.lower()
        data_in = data_in[model_feats] # [model.feature_names_in_]# [model_feats]
        preds_all = model.predict(data_in)
        preds_all = dl_obj.transformYData(out_feature=target_name, data=preds_all, t_type='power', 
                                           y_transform=y_transform)
        
        return y_pred_label, preds_all
    
    def checkBounds(self, df):
        mask = df['owp_tw_inchan'] > df['owp_tw_bf']
        df.loc[mask, ['owp_tw_bf', 'owp_tw_inchan']] = df.loc[mask, ['owp_tw_inchan', 'owp_tw_bf']].values

        mask = df['owp_y_inchan'] > df['owp_y_bf']
        df.loc[mask, ['owp_y_bf', 'owp_y_inchan']] = df.loc[mask, ['owp_y_inchan', 'owp_y_bf']].values
        return df

# --------------------------- A driver class --------------------------- #           
class RunDeploy:
    @staticmethod
    def main(argv):
        """ The driver class to run ML models
        
        Parameters 
        ----------
        argv: list
            taken from bash script
        """
        nthreads     = int(argv[0])
        SI           = True
        rand_state   = 105
        os.chdir('/mnt/d/Lynker/FEMA_HECRAS/bankfull_W_D/deployment')

        # Load data
        start = 0#2500000
        end = 500000#2647455
        print(end)
        dl_obj = dataloader.DataLoader(rand_state)
        dl_obj.readFiles(start, end)
        dl_obj.imputeData()

        # Load targets
        temp        = json.load(open('data/model_feature_names.json'))
        target_list = temp.get('out_features')
        # target_list = ['TW_bf', 'TW_in']
        out_vars    = []
        del temp

        # Additional parameters
        vote_flag   = False
        meta_flag   = False
        best_flag   = True
        file        = 'bf'
        model_type  = 'xgb'
        log_y_t     = False
        
        deploy_obj = DPModel(rand_state)
        
        results = []

        # Parallelize the for loop
        # for target_name in tqdm(target_list):
        #     # Call the deploy_obj.process_target function with the specified arguments
        #     result = deploy_obj.process_target(dl_obj, target_name, vote_flag, meta_flag, best_flag, file, model_type)
        #     # Append the result to the results list
        #     results.append(result)
        results = Parallel(n_jobs=nthreads, backend="multiprocessing")(delayed(deploy_obj.process_target)(dl_obj, target_name, vote_flag, meta_flag, best_flag, file, model_type) for target_name in tqdm(target_list))
        
        # Unpack the results
        for y_pred_label, preds_all in results:
            out_vars.append(y_pred_label)
            if log_y_t:
                dl_obj.data[y_pred_label] = np.exp(preds_all)
            else:
                dl_obj.data[y_pred_label] = preds_all
            if SI:
                dl_obj.data[y_pred_label] = dl_obj.data[y_pred_label] * 0.3048
    
        out_vars.append('FEATUREID')
        out_df = dl_obj.data[out_vars]
        out_df = deploy_obj.checkBounds(out_df)
        out_df.to_parquet('data/new_exports'+str(end)+'.parquet')
        print("\n ------------- ML estimates complete ----------- \n")
        return

if __name__ == "__main__":
    RunDeploy.main(sys.argv[1:])
    # RunDeploy.main([-1])