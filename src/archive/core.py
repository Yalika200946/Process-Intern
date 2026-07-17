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

_filename = None
_names = None
_descriptions = None
_units = None
_relevantColumns = None
_columnDescriptions = None
_columnUnits = None
_columnNames = None
_df = None
_traintime = None
_testtime = None
_df_train = None
_df_test = None
_targetColumns = None
_modelList = None
_X_train = None
_y_train = None
_X_test = None
_y_test = None
_maxEnrolWindow = None
_indexColumn = None

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
    """
    Initiate a pandas dataframe from file and provided metadata.

    PARAMS:
        filename: str - location of dataset file on disk in .csv format
        columns: List of list of column data [name, description, unit]
        irrelevantColumns: List of strings - columnNames excluded from the dataset

    RETURNS:
        df: Pandas dataframe
    """
    global _filename, _relevantColumns, _columnDescriptions, _columnUnits, _columnNames, _df

    columnNames = list(map(lambda el: el[0], columns))
    descriptions = list(map(lambda el: el[1], columns))
    units = list(map(lambda el: el[2], columns))

    relevantColumns = list(filter(
        lambda col: col not in irrelevantColumns,
        map(lambda el: el[0], columns)
    ))
    columnUnits = dict(zip(columnNames, units))
    columnDescriptions = dict(zip(columnNames, descriptions))

    _filename = filename
    _relevantColumns = relevantColumns
    _columnDescriptions = columnDescriptions
    _columnUnits = columnUnits
    _columnNames = columnNames

    df = utilities.initDataframe(
        filename,
        relevantColumns,
        columnDescriptions,
    )

    _df = df
    return df


def getTestTrainSplit(traintime, testtime):
    """
    Split training and testing rows into separate data frames.

    PARAMS:
        traintime: List of list of string pairs - start and end times for training
        testtime: List of string pair - start and end time for testing

    RETURNS:
        [df_train, df_test]
    """
    global _traintime, _testtime, _df, _df_train, _df_test

    _traintime = traintime
    _testtime = testtime

    df_train, df_test = utilities.getTestTrainSplit(_df, traintime, testtime)

    _df_train = df_train
    _df_test = df_test

    return [df_train, df_test]


def getFeatureTargetSplit(targetColumns):
    """
    Split feature and target columns into separate arrays.

    PARAMS:
        targetColumns: List of strings - column names used as output(target) values

    RETURNS:
        [X_train, y_train, X_test, y_test]
    """
    global _targetColumns, _X_train, _y_train, _X_test, _y_test

    _targetColumns = targetColumns

    X_train, y_train, X_test, y_test = utilities.getFeatureTargetSplit(
        _df_train,
        _df_test,
        targetColumns,
    )

    _X_train = X_train
    _y_train = y_train
    _X_test = X_test
    _y_test = y_test

    return [X_train, y_train, X_test, y_test]


def prepareDataframe(traintime, testtime, targetColumns):
    """
    Combination of getTestTrainSplit and getFeatureTargetSplit.

    RETURNS:
        [X_train, y_train, X_test, y_test]
    """
    getTestTrainSplit(traintime, testtime)
    return getFeatureTargetSplit(targetColumns)


def initModels(modelList):
    """
    Initiate the provided models by calculating required model parameters.
    """
    global _maxEnrolWindow, _indexColumn, _modelList, _df_test

    _maxEnrolWindow = utilities.findMaxEnrolWindow(modelList)
    _indexColumn = _df_test.iloc[_maxEnrolWindow:].index
    _modelList = modelList


def trainModels(retrain=False):
    """
    Train the models previously provided in the initModels method.
    """
    global _modelList, _filename, _targetColumns

    modelFuncs.trainModels(
        _modelList,
        _filename,
        _targetColumns,
        retrain
    )


def predictWithModels(plot=True, interpol=False, score=True):
    """
    Make predictions using previously defined models.

    RETURNS:
        [modelNames, metrics_train, metrics_test, columnsList, deviationsList]
    """
    global _modelList, _X_train, _y_train, _X_test, _y_test
    global _targetColumns, _indexColumn, _columnDescriptions, _columnUnits, _traintime

    modelNames, metrics_train, metrics_test, deviationsList, columnsList = utilities.predictWithModels(
        _modelList,
        _X_train,
        _y_train,
        _X_test,
        _y_test,
        _targetColumns
    )

    if score:
        prints.printModelScores(modelNames, metrics_train, metrics_test)
    if plot:
        plots.plotModelPredictions(
            plt,
            deviationsList,
            columnsList,
            _indexColumn,
            _columnDescriptions,
            _columnUnits,
            _traintime,
            interpol=interpol,
        )
    if score:
        plots.plotModelScores(plt, modelNames, metrics_train, metrics_test)

    return [modelNames, metrics_train, metrics_test, columnsList, deviationsList]


def predictWithModelsUsingDropout(numberOfPredictions=20):
    """
    Make predictions with RNN models using dropout at predict time.
    """
    global _modelList, _X_test, _y_test

    return utilities.predictMultipleWithModels(
        _modelList,
        _X_test,
        _y_test,
        numberOfPredictions,
    )


# ─── Model Factory Functions ───────────────────────────────────────

def MLP(
        name,
        layers=[128],
        dropout=None,
        l1_rate=0.0,
        l2_rate=0.0,
        activation=_default_MLP_args['activation'],
        loss=_default_MLP_args['loss'],
        optimizer=_default_MLP_args['optimizer'],
        metrics=_default_MLP_args['metrics'],
        epochs=_default_MLP_args['epochs'],
        batchSize=_default_MLP_args['batchSize'],
        verbose=_default_MLP_args['verbose'],
        validationSize=_default_MLP_args['validationSize'],
        testSize=_default_MLP_args['testSize'],
        callbacks=_default_MLP_args['callbacks'],
    ):
    global _X_train, _y_train

    mlpLayers = []
    for layerSize in layers:
        mlpLayers.append([layerSize, activation])

    model = models.kerasMLP(
        params={
            'name': name,
            'X_train': _X_train,
            'y_train': _y_train,
            'args': {
                'activation': activation,
                'loss': loss,
                'optimizer': optimizer,
                'metrics': metrics,
                'epochs': epochs,
                'batchSize': batchSize,
                'verbose': verbose,
                'callbacks': callbacks,
                'enrolWindow': 0,
                'validationSize': validationSize,
                'testSize': testSize,
            },
        },
        structure=mlpLayers,
        dropout=dropout,
        l1_rate=l1_rate,
        l2_rate=l2_rate,
    )

    return model


def LSTM(
    name,
    layers=[128],
    dropout=0.0,
    recurrentDropout=0.0,
    alpha=None,
    training=False,
    enrolWindow=_default_LSTM_args['enrolWindow'],
    activation=_default_LSTM_args['activation'],
    loss=_default_LSTM_args['loss'],
    optimizer=_default_LSTM_args['optimizer'],
    metrics=_default_LSTM_args['metrics'],
    epochs=_default_LSTM_args['epochs'],
    batchSize=_default_LSTM_args['batchSize'],
    verbose=_default_LSTM_args['verbose'],
    validationSize=_default_LSTM_args['validationSize'],
    testSize=_default_LSTM_args['testSize'],
    callbacks=_default_LSTM_args['callbacks'],
    ):
    global _X_train, _y_train

    model = models.kerasLSTM(
        params={
            'name': name,
            'X_train': _X_train,
            'y_train': _y_train,
            'args': {
                'activation': activation,
                'loss': loss,
                'optimizer': optimizer,
                'metrics': metrics,
                'epochs': epochs,
                'batchSize': batchSize,
                'verbose': verbose,
                'callbacks': callbacks,
                'enrolWindow': enrolWindow,
                'validationSize': validationSize,
                'testSize': testSize,
            },
        },
        layers=layers,
        dropout=dropout,
        recurrentDropout=recurrentDropout,
        alpha=alpha,
        training=training,
    )

    return model


def GRU(
    name,
    layers=[128],
    dropout=0.0,
    recurrentDropout=0.0,
    alpha=None,
    training=False,
    enrolWindow=_default_LSTM_args['enrolWindow'],
    activation=_default_LSTM_args['activation'],
    loss=_default_LSTM_args['loss'],
    optimizer=_default_LSTM_args['optimizer'],
    metrics=_default_LSTM_args['metrics'],
    epochs=_default_LSTM_args['epochs'],
    batchSize=_default_LSTM_args['batchSize'],
    verbose=_default_LSTM_args['verbose'],
    validationSize=_default_LSTM_args['validationSize'],
    testSize=_default_LSTM_args['testSize'],
    callbacks=_default_LSTM_args['callbacks'],
    ):
    global _X_train, _y_train

    model = models.kerasGRU(
        params={
            'name': name,
            'X_train': _X_train,
            'y_train': _y_train,
            'args': {
                'activation': activation,
                'loss': loss,
                'optimizer': optimizer,
                'metrics': metrics,
                'epochs': epochs,
                'batchSize': batchSize,
                'verbose': verbose,
                'callbacks': callbacks,
                'enrolWindow': enrolWindow,
                'validationSize': validationSize,
                'testSize': testSize,
            },
        },
        layers=layers,
        dropout=dropout,
        recurrentDropout=recurrentDropout,
        alpha=alpha,
        training=training,
    )

    return model


def Linear(name):
    global _X_train, _y_train

    return models.sklearnLinear(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def Linear_Regularized(name, alphas=(0.1, 1.0, 10.0), folds=10):
    global _X_train, _y_train

    return models.sklearnRidgeCV(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
        alphas=alphas,
        folds=folds,
    )


def ElasticNet(name, alphas=(0.1, 1.0, 10.0), l1_ratio=0.5):
    global _X_train, _y_train

    return models.sklearnElasticNetCV(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
        alphas=alphas,
        l1_ratio=l1_ratio,
    )


def DecisionTree(name):
    global _X_train, _y_train

    return models.sklearnDecisionTree(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def RandomForest(name):
    global _X_train, _y_train

    return models.sklearnRandomForest(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def BaggingRegressor(name):
    global _X_train, _y_train

    return models.sklearnBagging(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def AdaBoostRegressor(name):
    global _X_train, _y_train

    return models.sklearnAdaBoost(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def SupportVectorMachine(name):
    global _X_train, _y_train

    return models.sklearnSVM(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
    )


def Ensemble(name, modelList):
    global _X_train, _y_train

    return models.ensembleModel(
        params={'name': name, 'X_train': _X_train, 'y_train': _y_train},
        models=modelList,
    )


def Autoencoder_Regularized(
        name,
        l1_rate=10e-4,
        encodingDim=3,
        activation=_default_MLP_args['activation'],
        loss=_default_MLP_args['loss'],
        optimizer=_default_MLP_args['optimizer'],
        metrics=_default_MLP_args['metrics'],
        epochs=_default_MLP_args['epochs'],
        batchSize=_default_MLP_args['batchSize'],
        verbose=_default_MLP_args['verbose'],
        validationSize=_default_MLP_args['validationSize'],
        testSize=_default_MLP_args['testSize'],
        callbacks=_default_MLP_args['callbacks'],
    ):
    global _X_train

    return models.autoencoder_Regularized(
        params={
            'name': name,
            'X_train': _X_train,
            'args': {
                'activation': activation,
                'loss': loss,
                'optimizer': optimizer,
                'metrics': metrics,
                'epochs': epochs,
                'batchSize': batchSize,
                'verbose': verbose,
                'callbacks': callbacks,
                'enrolWindow': 0,
                'validationSize': validationSize,
                'testSize': testSize,
            },
        },
        l1_rate=l1_rate,
        encodingDim=encodingDim,
    )


def Autoencoder_Dropout(
        name,
        dropout=0.0,
        encodingDim=3,
        activation=_default_MLP_args['activation'],
        loss=_default_MLP_args['loss'],
        optimizer=_default_MLP_args['optimizer'],
        metrics=_default_MLP_args['metrics'],
        epochs=_default_MLP_args['epochs'],
        batchSize=_default_MLP_args['batchSize'],
        verbose=_default_MLP_args['verbose'],
        validationSize=_default_MLP_args['validationSize'],
        testSize=_default_MLP_args['testSize'],
        callbacks=_default_MLP_args['callbacks'],
    ):
    global _X_train

    return models.autoencoder_Dropout(
        params={
            'name': name,
            'X_train': _X_train,
            'args': {
                'activation': activation,
                'loss': loss,
                'optimizer': optimizer,
                'metrics': metrics,
                'epochs': epochs,
                'batchSize': batchSize,
                'verbose': verbose,
                'callbacks': callbacks,
                'enrolWindow': 0,
                'validationSize': validationSize,
                'testSize': testSize,
            },
        },
        dropout=dropout,
        encodingDim=encodingDim,
    )


# ─── Analysis Functions ────────────────────────────────────────────

def correlationMatrix(df):
    return analysis.correlationMatrix(df)


def pca(df, numberOfComponents, relevantColumns=None, columnDescriptions=None):
    return analysis.pca(df, numberOfComponents, relevantColumns, columnDescriptions)


def pcaPlot(df, timestamps=None, plotTitle=None):
    return analysis.pcaPlot(df, timestamps, plotTitle)


def pairplot(df):
    return analysis.pairplot(df)


def scatterplot(df):
    return analysis.scatterplot(df)


def correlationPlot(df, title="Correlation plot"):
    return analysis.correlationPlot(df, title)


def correlationDuoPlot(df1, df2, title1="Correlation plot 1", title2="Correlation plot 2"):
    return analysis.correlationDuoPlot(df1, df2, title1, title2)


def correlationDifferencePlot(df1, df2, title="Correlation difference plot"):
    return analysis.correlationDifferencePlot(df1, df2, title)


def valueDistribution(df, traintime, testtime, columnDescriptions, columnUnits):
    return analysis.valueDistribution(df, traintime, testtime, columnDescriptions, columnUnits)


def printCorrelationMatrix(covmat, df, columnNames=None):
    return prints.printCorrelationMatrix(covmat, df, columnNames)


def printExplainedVarianceRatio(pca):
    return prints.printExplainedVarianceRatio(pca)


# ─── Utility Functions ─────────────────────────────────────────────

def reset():
    global _filename, _names, _descriptions, _units, _relevantColumns
    global _columnDescriptions, _columnUnits, _columnNames, _df
    global _traintime, _testtime, _df_train, _df_test
    global _targetColumns, _modelList, _X_train, _y_train, _X_test, _y_test
    global _maxEnrolWindow, _indexColumn

    _filename = None
    _names = None
    _descriptions = None
    _units = None
    _relevantColumns = None
    _columnDescriptions = None
    _columnUnits = None
    _columnNames = None
    _df = None
    _traintime = None
    _testtime = None
    _df_train = None
    _df_test = None
    _targetColumns = None
    _modelList = None
    _X_train = None
    _y_train = None
    _X_test = None
    _y_test = None
    _maxEnrolWindow = None
    _indexColumn = None


def getCallbacks(patience_es, patience_rlr):
    return modelFuncs.getBasicCallbacks(patience_es=patience_es, patience_rlr=patience_rlr)


def setMLPCallbacks(patience_es, patience_rlr):
    global _default_MLP_args
    _default_MLP_args['callbacks'] = modelFuncs.getBasicCallbacks(
        patience_es=patience_es, patience_rlr=patience_rlr
    )


def setLSTMCallbacks(patience_es, patience_rlr):
    global _default_LSTM_args
    _default_LSTM_args['callbacks'] = modelFuncs.getBasicCallbacks(
        patience_es=patience_es, patience_rlr=patience_rlr
    )
