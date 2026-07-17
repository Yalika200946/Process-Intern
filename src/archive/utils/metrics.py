from sklearn.metrics import (
    r2_score,
    mean_squared_error,
    mean_absolute_error,
    max_error
)

import numpy as np

np.random.seed(100)


def calculateR2Score(y_true, y_pred):
    return r2_score(y_true, y_pred)


def calculateMSE(y_true, y_pred):
    return mean_squared_error(y_true, y_pred)


def calculateRMSE(y_true, y_pred):
    return np.sqrt(mean_squared_error(y_true, y_pred))


def calculateMAE(y_true, y_pred):
    return mean_absolute_error(y_true, y_pred)


def calculateMaxError(y_true, y_pred):
    if len(y_true.shape) > 1 and y_true.shape[1] > 1:
        return None
    return max_error(y_true, y_pred)


def calculateMAPE(y_true, y_pred):
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100


def calculateMetrics(y_true, y_pred):
    r2 = r2_score(y_true, y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_true, y_pred)

    if len(y_true.shape) > 1 and y_true.shape[1] > 1:
        maxerror = None
    else:
        maxerror = max_error(y_true, y_pred)

    return [r2, mse, rmse, mae, maxerror]
