import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

from keras.callbacks import EarlyStopping, ReduceLROnPlateau
import plots
import prints
import pickle
import numpy as np

np.random.seed(100)


def printModelSummary(model):
    if hasattr(model, "summary"):
        print(model.summary())
    elif hasattr(model, "model"):
        if hasattr(model.model, "summary"):
            printModelSummary(model.model)
    elif hasattr(model, "models"):
        print("Model is of type Ensemble Model")
        print("Sub model summaries will follow")
        print("-------------------------------")
        for mod in model.models:
            printModelSummary(mod)
    else:
        print("Simple models have no summary")


def printModelWeights(model):
    if hasattr(model, "summary"):
        for layer in model.layers:
            print(layer.get_config(), layer.get_weights())
    elif hasattr(model, "model"):
        if hasattr(model.model, "summary"):
            printModelWeights(model.model)
    elif hasattr(model, "models"):
        print("Model is of type Ensemble Model")
        print("Sub model summaries will follow")
        print("-------------------------------")
        for mod in model.models:
            printModelWeights(mod)
    else:
        if hasattr(model, "get_params"):
            print(model.get_params())
        else:
            print("No weights found")


def getBasicCallbacks(monitor="val_loss", patience_es=200, patience_rlr=80):
    return [
        EarlyStopping(
            monitor=monitor,
            patience=patience_es,
            verbose=1,
            restore_best_weights=True,
        ),
        ReduceLROnPlateau(
            monitor=monitor,
            factor=0.5,
            patience=patience_rlr,
            verbose=1,
            min_lr=1e-6,
        ),
    ]


def getRNNSplit(X, y, enrolWindow):
    X_rnn = []
    y_rnn = []
    for i in range(enrolWindow, len(X)):
        X_rnn.append(X[i - enrolWindow:i])
        y_rnn.append(y[i])
    return np.array(X_rnn), np.array(y_rnn)


def trainModels(modelList, filename, targetColumns, retrain=False):
    trainingSummary = {}
    for model in modelList:
        print(f"\nTraining model: {model.name}")
        prints.printHorizontalLine()

        model_filepath = ROOT_PATH + f'/src/ml/trained_models/{filename}_{model.name}'

        if not retrain:
            try:
                model.load(model_filepath)
                print(f"Loaded existing model: {model.name}")
                continue
            except (FileNotFoundError, OSError):
                pass

        model.train()

        if model.history is not None:
            history = model.history.history
            trainingSummary[model.name] = {
                'loss_final': min(history['loss']),
                'loss_actual': history['loss'][-1],
                'val_loss_final': min(history.get('val_loss', [0])),
                'length': len(history['loss']),
            }

        try:
            model.save(model_filepath)
        except Exception as e:
            print(f"Could not save model {model.name}: {e}")

    if trainingSummary:
        prints.printTrainingSummary(trainingSummary)
