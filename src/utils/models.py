import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

from sklearn.linear_model import LinearRegression, RidgeCV, ElasticNetCV
from sklearn.ensemble import (
    RandomForestRegressor,
    BaggingRegressor,
    AdaBoostRegressor,
)
from sklearn.svm import LinearSVR
from sklearn.tree import DecisionTreeRegressor
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.model_selection import train_test_split

from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, Input, LSTM, GRU, LeakyReLU
from keras.regularizers import l1, l2, l1_l2
from keras.callbacks import ModelCheckpoint

from copy import deepcopy
import pickle
import numpy as np
import tensorflow as tf
from modelFuncs import getRNNSplit

np.random.seed(100)
tf.random.set_seed(100)

CURRENT_MODEL_WEIGHTS_FILEPATH = ROOT_PATH + '/src/ml/trained_models/training_weights/'


class Args():
    def __init__(self, args):
        self.activation = args['activation']
        self.loss = args['loss']
        self.optimizer = args['optimizer']
        self.metrics = args['metrics']
        self.epochs = args['epochs']
        self.batchSize = args['batchSize']
        self.verbose = args['verbose']
        self.callbacks = args['callbacks']
        self.enrolWindow = args['enrolWindow']
        self.validationSize = args['validationSize']
        self.testSize = args['testSize']


class EnsembleModel():
    def __init__(self, models, X_train, y_train, modelType="Ensemble", name=None):
        maxEnrol = 0
        for model in models:
            if model.args is not None:
                enrol = model.args.enrolWindow
                if enrol is not None and enrol > maxEnrol:
                    maxEnrol = enrol

        self.maxEnrol = maxEnrol
        self.models = models
        self.MLmodel = None
        self.X_train = X_train
        self.y_train = y_train
        self.name = name
        self.history = None
        self.modelType = modelType
        self.args = None

    def train(self):
        preds = []
        for model in self.models:
            model.train()
            prediction = model.predict(model.X_train, model.y_train)
            if model.modelType == "RNN":
                preds.append(prediction[self.maxEnrol - model.args.enrolWindow:])
            else:
                preds.append(prediction[self.maxEnrol:])

        train = preds[0]
        for pred in preds[1:]:
            train = np.concatenate((train, pred), axis=1)
        self.MLmodel = sklearnLinear(
            params={
                'name': 'Linear model of ensemble',
                'X_train': train,
                'y_train': self.y_train[self.maxEnrol:],
            },
        )
        self.MLmodel.train()

    def predict(self, X, y):
        preds = []
        for model in self.models:
            prediction = model.predict(X, y)
            if model.modelType == "RNN":
                preds.append(prediction[self.maxEnrol - model.args.enrolWindow:])
            else:
                preds.append(prediction[self.maxEnrol:])

        combined = preds[0]
        for pred in preds[1:]:
            combined = np.concatenate((combined, pred), axis=1)
        return self.MLmodel.predict(combined, y[self.maxEnrol:])


class MachineLearningModel():
    def __init__(self, model, X_train, y_train, scaler=None, modelType="ML", name=None, args=None, history=None):
        self.model = model
        self.X_train = X_train
        self.y_train = y_train
        self.scaler = scaler
        self.name = name
        self.modelType = modelType
        self.history = history
        self.args = Args(args) if args is not None else None

    def train(self):
        if self.modelType == "Keras" or self.modelType == "RNN":
            self.history = self.model.fit(
                self.X_train,
                self.y_train,
                epochs=self.args.epochs,
                batch_size=self.args.batchSize,
                verbose=self.args.verbose,
                validation_split=self.args.validationSize,
                callbacks=self.args.callbacks,
            )
        else:
            self.model.fit(self.X_train, self.y_train)

    def predict(self, X, y):
        if self.scaler is not None:
            X = self.scaler.transform(X)
        prediction = self.model.predict(X)
        return prediction

    def save(self, filepath):
        if self.modelType in ["Keras", "RNN"]:
            self.model.save(filepath + '.h5')
        else:
            with open(filepath + '.pkl', 'wb') as f:
                pickle.dump(self.model, f)

    def load(self, filepath):
        if self.modelType in ["Keras", "RNN"]:
            from keras.models import load_model
            self.model = load_model(filepath + '.h5')
        else:
            with open(filepath + '.pkl', 'rb') as f:
                self.model = pickle.load(f)


def kerasMLP(params, structure, dropout=None, l1_rate=0.0, l2_rate=0.0):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']
    args = params['args']

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    n_features = X_train_scaled.shape[1]
    n_outputs = y_train.shape[1] if len(y_train.shape) > 1 else 1

    model = Sequential()
    for i, (layerSize, activation) in enumerate(structure):
        if i == 0:
            model.add(Dense(
                layerSize,
                activation=activation,
                input_shape=(n_features,),
                kernel_regularizer=l1_l2(l1=l1_rate, l2=l2_rate),
            ))
        else:
            model.add(Dense(
                layerSize,
                activation=activation,
                kernel_regularizer=l1_l2(l1=l1_rate, l2=l2_rate),
            ))
        if dropout is not None:
            model.add(Dropout(dropout))

    model.add(Dense(n_outputs))

    model.compile(
        loss=args['loss'],
        optimizer=args['optimizer'],
        metrics=args['metrics'],
    )

    return MachineLearningModel(
        model=model,
        X_train=X_train_scaled,
        y_train=y_train,
        scaler=scaler,
        modelType="Keras",
        name=name,
        args=args,
    )


def kerasLSTM(params, layers, dropout=0.0, recurrentDropout=0.0, alpha=None, training=False):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']
    args = params['args']

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    enrolWindow = args['enrolWindow']
    X_train_rnn, y_train_rnn = getRNNSplit(X_train_scaled, y_train, enrolWindow)

    n_features = X_train_scaled.shape[1]
    n_outputs = y_train.shape[1] if len(y_train.shape) > 1 else 1

    model = Sequential()
    for i, layerSize in enumerate(layers):
        return_sequences = i < len(layers) - 1
        if i == 0:
            model.add(LSTM(
                layerSize,
                activation=args['activation'],
                input_shape=(enrolWindow, n_features),
                dropout=dropout,
                recurrent_dropout=recurrentDropout,
                return_sequences=return_sequences,
            ))
        else:
            model.add(LSTM(
                layerSize,
                activation=args['activation'],
                dropout=dropout,
                recurrent_dropout=recurrentDropout,
                return_sequences=return_sequences,
            ))
        if alpha is not None:
            model.add(LeakyReLU(alpha=alpha))

    model.add(Dense(n_outputs))

    model.compile(
        loss=args['loss'],
        optimizer=args['optimizer'],
        metrics=args['metrics'],
    )

    return MachineLearningModel(
        model=model,
        X_train=X_train_rnn,
        y_train=y_train_rnn,
        scaler=scaler,
        modelType="RNN",
        name=name,
        args=args,
    )


def kerasGRU(params, layers, dropout=0.0, recurrentDropout=0.0, alpha=None, training=False):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']
    args = params['args']

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    enrolWindow = args['enrolWindow']
    X_train_rnn, y_train_rnn = getRNNSplit(X_train_scaled, y_train, enrolWindow)

    n_features = X_train_scaled.shape[1]
    n_outputs = y_train.shape[1] if len(y_train.shape) > 1 else 1

    model = Sequential()
    for i, layerSize in enumerate(layers):
        return_sequences = i < len(layers) - 1
        if i == 0:
            model.add(GRU(
                layerSize,
                activation=args['activation'],
                input_shape=(enrolWindow, n_features),
                dropout=dropout,
                recurrent_dropout=recurrentDropout,
                return_sequences=return_sequences,
            ))
        else:
            model.add(GRU(
                layerSize,
                activation=args['activation'],
                dropout=dropout,
                recurrent_dropout=recurrentDropout,
                return_sequences=return_sequences,
            ))
        if alpha is not None:
            model.add(LeakyReLU(alpha=alpha))

    model.add(Dense(n_outputs))

    model.compile(
        loss=args['loss'],
        optimizer=args['optimizer'],
        metrics=args['metrics'],
    )

    return MachineLearningModel(
        model=model,
        X_train=X_train_rnn,
        y_train=y_train_rnn,
        scaler=scaler,
        modelType="RNN",
        name=name,
        args=args,
    )


def sklearnLinear(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = LinearRegression()

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Linear",
        name=name,
    )


def sklearnRidgeCV(params, alphas=(0.1, 1.0, 10.0), folds=10):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = RidgeCV(alphas=alphas, cv=folds)

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Linear",
        name=name,
    )


def sklearnElasticNetCV(params, alphas=(0.1, 1.0, 10.0), l1_ratio=0.5):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = ElasticNetCV(alphas=alphas, l1_ratio=l1_ratio)

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Linear",
        name=name,
    )


def sklearnDecisionTree(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = DecisionTreeRegressor()

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Tree",
        name=name,
    )


def sklearnRandomForest(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = RandomForestRegressor(n_estimators=100)

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Tree",
        name=name,
    )


def sklearnBagging(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = BaggingRegressor(n_estimators=100)

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Ensemble",
        name=name,
    )


def sklearnAdaBoost(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = AdaBoostRegressor(n_estimators=100)

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="Ensemble",
        name=name,
    )


def sklearnSVM(params):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    model = LinearSVR()

    return MachineLearningModel(
        model=model,
        X_train=X_train,
        y_train=y_train,
        modelType="SVM",
        name=name,
    )


def ensembleModel(params, models):
    X_train = params['X_train']
    y_train = params['y_train']
    name = params['name']

    return EnsembleModel(
        models=models,
        X_train=X_train,
        y_train=y_train,
        name=name,
    )


def autoencoder_Regularized(params, l1_rate=10e-4, encodingDim=3):
    X_train = params['X_train']
    name = params['name']
    args = params['args']

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    n_features = X_train_scaled.shape[1]

    input_layer = Input(shape=(n_features,))
    encoded = Dense(encodingDim, activation='relu', activity_regularizer=l1(l1_rate))(input_layer)
    decoded = Dense(n_features, activation='sigmoid')(encoded)

    model = Model(input_layer, decoded)
    model.compile(
        loss=args['loss'],
        optimizer=args['optimizer'],
        metrics=args['metrics'],
    )

    return MachineLearningModel(
        model=model,
        X_train=X_train_scaled,
        y_train=X_train_scaled,
        scaler=scaler,
        modelType="Autoencoder",
        name=name,
        args=args,
    )


def autoencoder_Dropout(params, dropout=0.0, encodingDim=3):
    X_train = params['X_train']
    name = params['name']
    args = params['args']

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    n_features = X_train_scaled.shape[1]

    input_layer = Input(shape=(n_features,))
    encoded = Dense(encodingDim, activation='relu')(input_layer)
    encoded = Dropout(dropout)(encoded)
    decoded = Dense(n_features, activation='sigmoid')(encoded)

    model = Model(input_layer, decoded)
    model.compile(
        loss=args['loss'],
        optimizer=args['optimizer'],
        metrics=args['metrics'],
    )

    return MachineLearningModel(
        model=model,
        X_train=X_train_scaled,
        y_train=X_train_scaled,
        scaler=scaler,
        modelType="Autoencoder",
        name=name,
        args=args,
    )
