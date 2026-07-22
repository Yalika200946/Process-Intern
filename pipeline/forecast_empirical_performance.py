"""Short-term empirical relative-performance forecasts; not confirmed fouling forecasts."""
from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def linear_forecast(frame:pd.DataFrame,lookback:int=180,horizons=(30,90))->tuple[pd.DataFrame,dict]:
    g=frame.sort_values("timestamp").dropna(subset=["relative_ua_empirical"]).tail(lookback).copy()
    hx=str(g.hx_id.iloc[0]) if len(g) else "UNKNOWN"
    if len(g)<60:return pd.DataFrame(),{"hx_id":hx,"status":"PARTIAL","reason":"INSUFFICIENT_RECENT_VALID_RECORDS","valid_records":len(g)}
    x=(g.timestamp-g.timestamp.iloc[0]).dt.total_seconds().to_numpy()/86400;y=g.relative_ua_empirical.to_numpy();design=np.c_[np.ones(len(x)),x];beta=np.linalg.lstsq(design,y,rcond=None)[0];res=y-design@beta;sigma=float(np.std(res,ddof=2));last=g.timestamp.iloc[-1];rows=[]
    for h in horizons:
        pred=float(beta[0]+beta[1]*(x[-1]+h));rows.append({"hx_id":hx,"forecast_date":last+pd.Timedelta(days=h),"horizon_days":h,"relative_ua_forecast":pred,"prediction_lower":pred-1.96*sigma,"prediction_upper":pred+1.96*sigma,"status":"EXPLORATORY","clean_condition_confirmed":False,"interpretation":"Trend against empirical reference; not confirmed fouling forecast."})
    hold=max(14,int(len(g)*.2));train=g.iloc[:-hold];test=g.iloc[-hold:];xt=(train.timestamp-train.timestamp.iloc[0]).dt.total_seconds().to_numpy()/86400;bt=np.linalg.lstsq(np.c_[np.ones(len(xt)),xt],train.relative_ua_empirical.to_numpy(),rcond=None)[0];xv=(test.timestamp-train.timestamp.iloc[0]).dt.total_seconds().to_numpy()/86400;pred=np.c_[np.ones(len(xv)),xv]@bt;actual=test.relative_ua_empirical.to_numpy();persistence=np.repeat(train.relative_ua_empirical.iloc[-1],len(test))
    summary={"hx_id":hx,"status":"EXPLORATORY","valid_records":len(g),"lookback_records":lookback,"slope_relative_ua_per_day":beta[1],"holdout_records":len(test),"linear_rmse":float(np.sqrt(np.mean((actual-pred)**2))),"persistence_rmse":float(np.sqrt(np.mean((actual-persistence)**2))),"condition_threshold_status":"BLOCKED","threshold_blocker":"NO_APPROVED_RELATIVE_PERFORMANCE_THRESHOLD","forecast_confidence":"LOW" if sigma>.1 else "MEDIUM","clean_condition_confirmed":False}
    return pd.DataFrame(rows),summary

def main():
    source=ROOT/"reports/tables/mvp_real_data/empirical_relative_performance/relative_performance_timeseries.csv";frame=pd.read_csv(source);frame["timestamp"]=pd.to_datetime(frame.timestamp,utc=True).dt.tz_convert("Asia/Bangkok");forecasts=[];summaries=[];figdir=ROOT/"reports/figures/mvp_real_data/forecast";figdir.mkdir(parents=True,exist_ok=True)
    for hx,g in frame.groupby("hx_id"):
        forecast,summary=linear_forecast(g);summaries.append(summary)
        if forecast.empty:continue
        forecasts.append(forecast);history=g.sort_values("timestamp").tail(365);fig,ax=plt.subplots(figsize=(12,5));ax.plot(history.timestamp,history.relative_ua_empirical,lw=.7,label="Historical relative UA (empirical)");ax.plot(forecast.forecast_date,forecast.relative_ua_forecast,"o--",label="Exploratory linear forecast");ax.fill_between(forecast.forecast_date,forecast.prediction_lower,forecast.prediction_upper,alpha=.2);ax.axhline(1,color="green",ls="--");ax.set(xlabel="Time (Asia/Bangkok)",ylabel="Relative UA (-)",title=f"{hx} - exploratory empirical-performance forecast");ax.legend();fig.tight_layout();fig.savefig(figdir/f"{hx}_relative_performance_forecast.png",dpi=140);plt.close(fig)
    out=ROOT/"reports/tables/mvp_real_data/forecast";out.mkdir(parents=True,exist_ok=True);pd.concat(forecasts,ignore_index=True).to_csv(out/"empirical_relative_forecasts.csv",index=False);pd.DataFrame(summaries).to_csv(out/"forecast_summary.csv",index=False);print(pd.DataFrame(summaries).to_string(index=False))
if __name__=="__main__":main()
