"""Fit curves in latent space"""

import warnings
warnings.filterwarnings("ignore")

import pickle
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from scipy.optimize import curve_fit
from scipy.stats import linregress
from mpl_toolkits.mplot3d import Axes3D

# Fit a straight line to the final time points of the (node1, node2) curve. 
# Add time points until R^2 falls under tol_r2, which means the curve is no longer straight. 
# Requires at least 5 data points for a good fit
def fit_vt_vm(node1, node2, tol_r2=0.99):
    n_points = 1
    r2 = 1
    while (r2 > tol_r2) and (n_points < len(node1)):
        n_points += 1
        slope,_,r2,_,_ = linregress(node1[-n_points:], node2[-n_points:])

    if n_points > 5:
        return slope
    else:
        return np.nan


# Compute ratio vt / vm experiment-wide
def compute_vt_vm(df):
    slopes = pd.DataFrame([], index=df.index.droplevel("Time").unique(), columns=["slope"])
    # Fit a straight line to as as many final points as possible (at least 5)
    for idx in slopes.index:
        slopes.loc[idx] = fit_vt_vm(df.loc[idx,"Node 1"], df.loc[idx,"Node 2"])

    # Return mean or median dropping conditions for which no slope could be reliably calculated (n_points <= 5)
    median_slope = slopes.dropna().median().values[0]
    mean_slope = slopes.dropna().mean().values[0]
    print("\tMedian slope:\t",np.around(median_slope,2))
    print("\tMean slope:\t",np.around(mean_slope,2))
    return mean_slope


# Piecewise ballistic function
def ballistic(times, v_0, theta, t_0, v_t):
    
    # Only keep unique values in times vector (which has double entries)
    times=np.unique(times)
    
    # Initialize some variables
    x = np.zeros(times.shape)
    y = np.zeros(times.shape)
    v_x = v_0 * np.cos(theta * 2 * np.pi / 360)
    v_y = v_0 * np.sin(theta * 2 * np.pi / 360)
    v_m = v_t / vt_vm_ratio
    
    # Phase 1
    prop = (times <= t_0)
    x[prop] = v_x * times[prop]
    y[prop] = v_y * times[prop]
    
    # Phase 2
    r0 = [v_x*t_0,v_y*t_0]  # Position at the end of the propulsion phase
    delta_t = times[~prop] - t_0
    
    x[~prop] = (v_x + v_m) * (1-np.exp(-2*delta_t))/2 - v_m * delta_t + r0[0]
    y[~prop] = (v_y + v_t) * (1-np.exp(-2*delta_t))/2 - v_t * delta_t + r0[1]
    
    return np.array([x, y]).flatten()


# Find the best fit for each time course in the DataFrame. 
def fit_all_curves(df):
    # Initialize a dataframe that will record parameters fitted to each curve. 
    cols = ["v_0", "theta", "t_0", "v_t", "var v_0", "var theta", "var t_0", "var v_t"]
    df_params = pd.DataFrame([], index=df.index.droplevel("Time").unique(), columns=cols)
    times=np.tile(df.index.get_level_values("Time").astype("int")/time_scale,[2])    
    
    # Fit each curve, then return the parameters
    for idx in df_params.index:
        peptide = idx[df_params.index.names.index("Peptide")]

        bounds = [(0, -135, 0, 0), (20, 90, 5, 20)]
        p0 = [3, -90, 0., 3]

        # Each row contains one node, each column is one time point. Required by curve_fit
        popt, pcov = curve_fit(ballistic, xdata=times, ydata=df.loc[idx,:].values.T.flatten(), p0=p0, bounds=bounds)

        df_params.loc[idx, ["v_0", "theta", "t_0", "v_t"]] = popt
        df_params.loc[idx, ["var v_0", "var theta", "var t_0", "var v_t"]] = np.diag(pcov)
    
    return df_params


time_scale=20
filepath="output/analysis/integral/"
cytokines="IFNg+IL-2+IL-6+IL-17A+TNFa"

tcellnumbers=["100k","30k","10k","3k"]
peptides=["N4","Q4","T4","V4"]
concentrations=["1uM","100nM","10nM","1nM"]

colors=sns.color_palette('deep', 4)
markers=["o","X","s","P"]
sizes=[50,30,20,10]

# Ugly way to define color dictionary for each of the variables
color_dict={var:color for var,color in zip(tcellnumbers+peptides+concentrations,colors+colors+colors)}
marker_dict={var:marker for var,marker in zip(tcellnumbers+peptides+concentrations,markers+markers+markers)}
size_dict={var:size for var,size in zip(tcellnumbers+peptides+concentrations,sizes+sizes+sizes)}

peptide_dict={pep:i for pep,i in zip(peptides,range(len(peptides)))}

df_all_params=pd.DataFrame([],columns=["TCellNumber","Data","Peptide","Concentration","v_0","t_0","theta"])

tcellnumber_experiments=["PeptideComparison_OT1_Timeseries_"+num for num in ["21","22","23"]]+["TCellNumber_OT1_Timeseries_7","Activation_TCellNumber_1"]
#,"TCellNumber_1"]

for exp in tcellnumber_experiments:
	print(exp)

	# Load data
	df=pd.read_hdf("output/dataframes/%s.hdf"%exp)
	df=df.loc[:,("integral",cytokines.split("+"))]
	df_min,df_max=pd.read_pickle(filepath+"/train-min-max.pkl")
	df=(df - df_min)/(df_max - df_min)

	mlp=pickle.load(open(filepath+"mlp.pkl", "rb"))

	# Project on latent space
	df=pd.DataFrame(np.dot(df,mlp.coefs_[0]),index=df.index,columns=["Node 1","Node 2"])

	# Fit curves
	vt_vm_ratio = compute_vt_vm(df)
	df_params = fit_all_curves(df)

	# From Activation_TCellNumber_1 dataset, only take None
	if "Activation" in exp:
		print(df_params)
		df_params=df_params.loc["Naive"]
		df=df.loc["Naive"]
	df_params["Data"]=exp
	df_all_params=pd.concat([df_all_params,df_params.reset_index()])

	print(df_params.index.levels)

	# Show parameter relationships
	if exp == "TCellNumber_1":
		tcellnumbers_=["200k", "80k", "32k", "16k", "8k", "2k"]
	else:
		tcellnumbers_=tcellnumbers

	h=sns.relplot(data=df_params.reset_index(), x="t_0",y="v_0",
		hue="TCellNumber", hue_order=tcellnumbers_,
		style="Peptide",style_order=peptides)
	h.ax.set(title=exp)
	# plt.savefig("figures/fitting/v0-t0-%s.pdf"%exp,bbox_to_inches='tight')

	# Compute latent space coordinates from parameters fits
	df_fit=df.copy()
	for idx in df_params.index:
		v_0, theta, t_0, v_t = df_params.loc[idx,["v_0","theta","t_0","v_t"]]
		times = df_fit.loc[idx,:].index.get_level_values("Time").astype("float")/time_scale
		df_fit.loc[idx,:]=ballistic(times, v_0, theta, t_0, v_t).reshape(2,-1).T

	# Compare fit vs splines
	df["Processing type"]="Splines"
	df_fit["Processing type"]="Fit"

	df_compare=pd.concat([df,df_fit])
	df_compare.set_index("Processing type",inplace=True,append=True)

	sns.relplot(data=df_compare.reset_index(),kind="line",sort=False,x="Node 1",y="Node 2",
				hue="Peptide",hue_order=["N4","Q4","T4","V4","G4","E1"],
				size="Concentration",size_order=["1uM","100nM","10nM","1nM"],
				style="Processing type",dashes=["",(1,1)],col=df.index.names[0])
	# plt.savefig("figures/fitting/compare-splines-with-fit-%s.pdf"%exp)

df_all_params.to_pickle(filepath+"all_fit_params.pkl")
plt.show()
