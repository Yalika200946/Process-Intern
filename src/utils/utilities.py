import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
import metrics
import plots
import prints

np.random.seed(100)
tf.random.set_seed(100)


def getColorScheme():
    return {
        'primary': '#000080',
        'secondary': '#2ca25f',
        'tertiary': '#8856a7',
        'quaternary': '#43a2ca',
        'quinary': '#e34a33',
        'senary': '#636363',
    }


def initDataframe(filename, relevantColumns, labelNames):
    df = readDataFile(filename)
    df = getDataWithTimeIndex(df)
    df = df.dropna()

    if relevantColumns is not None:
        df = dropIrrelevantColumns(df, [relevantColumns, labelNames])

    return df


def readDataFile(filename):
    ext = filename[-4:]
    if ext == '.csv':
        df = pd.read_csv(filename)
        if 'Date' in df.columns or 'date' in df.columns:
            date_col = 'Date' if 'Date' in df.columns else 'date'
            df['Date'] = pd.to_datetime(df[date_col], dayfirst=True)
            if date_col != 'Date':
                df = df.drop(date_col, axis=1)
        elif 'Time' in df.columns or 'time' in df.columns:
            time_col = 'Time' if 'Time' in df.columns else 'time'
            df['Date'] = pd.to_datetime(df[time_col], dayfirst=True)
            df = df.drop(time_col, axis=1)
    elif ext in ['.xls', 'xlsx']:
        df = pd.read_excel(filename)
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
        elif 'time' in df.columns:
            df['Date'] = pd.to_datetime(df['time'], dayfirst=True)
            df = df.drop('time', axis=1)
    else:
        raise ValueError("Could not load data from file. Filename must be .csv or .xlsx format")
    return df


def getDataWithTimeIndex(df, dateColumn='Date'):
    if dateColumn in df.columns:
        df = df.set_index(dateColumn, inplace=False)
    else:
        raise ValueError('No date column named ' + dateColumn + '.')
    return df


def dropIrrelevantColumns(df, args):
    relevantColumns, columnDescriptions = args

    print("Columns before removal: ")
    prints.printColumns(df, columnDescriptions)

    dfcolumns = df.columns
    for column in dfcolumns:
        if column not in relevantColumns:
            df = df.drop(column, axis=1)

    prints.printEmptyLine()
    print("Columns after removal: ")
    prints.printColumns(df, columnDescriptions)
    prints.printEmptyLine()

    return df


def getTestTrainSplit(df, traintime, testtime):
    if isinstance(traintime[0], str):
        start_train, end_train = traintime
        df_train = getDataByTimeframe(df, start_train, end_train)
    else:
        start_train, end_train = traintime[0]
        df_train = getDataByTimeframe(df, start_train, end_train)
        for start_train, end_train in traintime[1:]:
            nextDf = getDataByTimeframe(df, start_train, end_train)
            df_train = pd.concat([df_train, nextDf])

    if isinstance(testtime[0], str):
        start_test, end_test = testtime
        df_test = getDataByTimeframe(df, start_test, end_test)
    else:
        start_test, end_test = testtime[0]
        df_test = getDataByTimeframe(df, start_test, end_test)
        for start_test, end_test in testtime[1:]:
            nextDf = getDataByTimeframe(df, start_test, end_test)
            df_test = pd.concat([df_test, nextDf])

    return df_train, df_test


def getDataByTimeframe(df, start, end):
    return df.loc[start:end]


def getFeatureTargetSplit(df_train, df_test, targetColumns):
    X_train = df_train.drop(targetColumns, axis=1).values
    y_train = df_train[targetColumns].values
    X_test = df_test.drop(targetColumns, axis=1).values
    y_test = df_test[targetColumns].values

    return X_train, y_train, X_test, y_test


def findMaxEnrolWindow(modelList):
    maxEnrolWindow = 0
    for model in modelList:
        if model.args is not None:
            enrol = model.args.enrolWindow
            if enrol is not None and enrol > maxEnrolWindow:
                maxEnrolWindow = enrol
    return maxEnrolWindow


def predictWithModels(modelList, X_train, y_train, X_test, y_test, targetColumns):
    modelNames = []
    metrics_train_list = []
    metrics_test_list = []
    deviationsList = []
    columnsList = []

    maxEnrolWindow = findMaxEnrolWindow(modelList)

    for model in modelList:
        prediction_train = model.predict(X_train, y_train)
        prediction_test = model.predict(X_test, y_test)

        if model.modelType == "RNN":
            enrol = model.args.enrolWindow
            offset = maxEnrolWindow - enrol
            prediction_test = prediction_test[offset:]
            prediction_train = prediction_train[offset:]
            y_test_eval = y_test[maxEnrolWindow:]
            y_train_eval = y_train[maxEnrolWindow:]
        else:
            prediction_test = prediction_test[maxEnrolWindow:]
            prediction_train = prediction_train[maxEnrolWindow:]
            y_test_eval = y_test[maxEnrolWindow:]
            y_train_eval = y_train[maxEnrolWindow:]

        met_train = metrics.calculateMetrics(y_train_eval, prediction_train)
        met_test = metrics.calculateMetrics(y_test_eval, prediction_test)

        modelNames.append(model.name)
        metrics_train_list.append(met_train)
        metrics_test_list.append(met_test)

        deviations = y_test_eval - prediction_test
        deviationsList.append(deviations)
        columnsList.append({
            'name': model.name,
            'prediction': prediction_test,
            'actual': y_test_eval,
            'targetColumns': targetColumns,
        })

    return modelNames, metrics_train_list, metrics_test_list, deviationsList, columnsList


def predictMultipleWithModels(modelList, X_test, y_test, numberOfPredictions=20):
    predictions = []
    means = []
    standarddevs = []

    for model in modelList:
        preds = []
        for _ in range(numberOfPredictions):
            pred = model.predict(X_test, y_test)
            preds.append(pred)
        preds = np.array(preds)
        mean = np.mean(preds, axis=0)
        std = np.std(preds, axis=0)
        predictions.append(preds)
        means.append(mean)
        standarddevs.append(std)

    return predictions, means, standarddevs
