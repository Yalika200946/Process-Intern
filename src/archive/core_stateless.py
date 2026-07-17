import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

import matplotlib.pyplot as plt

import utilities
import metrics
import models
import modelFuncs
import plots
import prints
import analysis

import numpy as np
import tensorflow as tf

np.random.seed(100)
tf.random.set_seed(100)

_default_MLP_args = {
    'activation': 'relu',
    'loss': 'mean_absolute_error',
    'optimizer': 'adam',
    'metrics': ['mean_absolute_error'],
    'epochs': 500,
    'batchSize': 128 * 2,
    'verbose': 1,
    'callbacks': modelFuncs.getBasicCallbacks(patience_es=60, patience_rlr=40),
    'enrolWindow': 0,
    'validationSize': 0.2,
    'testSize': 0.2,
}

_default_LSTM_args = {
    'activation': 'tanh',
    'loss': 'mean_absolute_error',
    'optimizer': 'adam',
    'metrics': ['mean_absolute_error'],
    'epochs': 500,
    'batchSize': 128 * 2,
    'verbose': 1,
    'callbacks': modelFuncs.getBasicCallbacks(patience_es=60, patience_rlr=40),
    'enrolWindow': 12,
    'validationSize': 0.2,
    'testSize': 0.2,
}


def initDataframe(filename, columns, irrelevantColumns):
    columnNames = list(map(lambda el: el[0], columns))
    descriptions = list(map(lambda el: el[1], columns))
    units = list(map(lambda el: el[2], columns))

    relevantColumns = list(filter(
        lambda col: col not in irrelevantColumns,
        map(lambda el: el[0], columns)
    ))
    columnUnits = dict(zip(columnNames, units))
    columnDescriptions = dict(zip(columnNames, descriptions))

    df = utilities.initDataframe(filename, relevantColumns, columnDescriptions)

    return df, relevantColumns, columnDescriptions, columnUnits, columnNames


def getTestTrainSplit(df, traintime, testtime):
    return utilities.getTestTrainSplit(df, traintime, testtime)


def getFeatureTargetSplit(df_train, df_test, targetColumns):
    return utilities.getFeatureTargetSplit(df_train, df_test, targetColumns)


def MLP(name, X_train, y_train, layers=[128], dropout=None, l1_rate=0.0, l2_rate=0.0, **kwargs):
    args = {**_default_MLP_args, **kwargs}
    mlpLayers = [[layerSize, args['activation']] for layerSize in layers]

    return models.kerasMLP(
        params={
            'name': name,
            'X_train': X_train,
            'y_train': y_train,
            'args': args,
        },
        structure=mlpLayers,
        dropout=dropout,
        l1_rate=l1_rate,
        l2_rate=l2_rate,
    )


def LSTM(name, X_train, y_train, layers=[128], dropout=0.0, recurrentDropout=0.0, alpha=None, training=False, **kwargs):
    args = {**_default_LSTM_args, **kwargs}

    return models.kerasLSTM(
        params={
            'name': name,
            'X_train': X_train,
            'y_train': y_train,
            'args': args,
        },
        layers=layers,
        dropout=dropout,
        recurrentDropout=recurrentDropout,
        alpha=alpha,
        training=training,
    )


def GRU(name, X_train, y_train, layers=[128], dropout=0.0, recurrentDropout=0.0, alpha=None, training=False, **kwargs):
    args = {**_default_LSTM_args, **kwargs}

    return models.kerasGRU(
        params={
            'name': name,
            'X_train': X_train,
            'y_train': y_train,
            'args': args,
        },
        layers=layers,
        dropout=dropout,
        recurrentDropout=recurrentDropout,
        alpha=alpha,
        training=training,
    )


def Linear(name, X_train, y_train):
    return models.sklearnLinear(
        params={'name': name, 'X_train': X_train, 'y_train': y_train},
    )


def Linear_Regularized(name, X_train, y_train, alphas=(0.1, 1.0, 10.0), folds=10):
    return models.sklearnRidgeCV(
        params={'name': name, 'X_train': X_train, 'y_train': y_train},
        alphas=alphas,
        folds=folds,
    )


def RandomForest(name, X_train, y_train):
    return models.sklearnRandomForest(
        params={'name': name, 'X_train': X_train, 'y_train': y_train},
    )


def DecisionTree(name, X_train, y_train):
    return models.sklearnDecisionTree(
        params={'name': name, 'X_train': X_train, 'y_train': y_train},
    )


def Ensemble(name, X_train, y_train, modelList):
    return models.ensembleModel(
        params={'name': name, 'X_train': X_train, 'y_train': y_train},
        models=modelList,
    )
