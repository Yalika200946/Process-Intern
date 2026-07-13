import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

import utilities
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

np.random.seed(100)

colors = list(utilities.getColorScheme().values())
sns.set(context='paper', style='whitegrid', palette=sns.color_palette(colors))


def correlationMatrix(df):
    if 'Date' in df.columns:
        df = df.drop('Date', axis=1, inplace=False)
    if 'Index' in df.columns:
        df = df.drop('Index', axis=1, inplace=False)

    X = df.values
    standardScaler = StandardScaler()
    X = standardScaler.fit_transform(X)
    covMat = np.cov(X.T)

    return covMat


def pca(df, numberOfComponents, relevantColumns=None, columnDescriptions=None):
    if 'Date' in df.columns:
        df = df.drop('Date', axis=1, inplace=False)
    if 'Index' in df.columns:
        df = df.drop('Index', axis=1, inplace=False)

    X = df.values
    standardScaler = StandardScaler()
    X = standardScaler.fit_transform(X)

    if numberOfComponents < 1 or numberOfComponents > df.shape[1]:
        numberOfComponents = df.shape[1]

    pca_model = PCA(n_components=numberOfComponents)
    pca_model.fit(X)

    return pca_model


def pcaPlot(df, timestamps=None, plotTitle=None):
    if timestamps is not None:
        traintime, testtime, validtime = timestamps
        df_train, df_test = utilities.getTestTrainSplit(df, traintime, testtime)
        train_vals = df_train.values
    else:
        train_vals = df.values

    sc = StandardScaler()
    train_vals = sc.fit_transform(train_vals)

    numberOfComponents = 2
    pca_model = PCA(n_components=numberOfComponents)
    pca_model.fit(train_vals)

    X = df.values
    X = sc.transform(X)
    X = pca_model.transform(X)

    df_pca = pd.DataFrame(data=X, index=df.index, columns=['pca1', 'pca2'])

    fig, ax = plt.subplots(1, 1, figsize=(10, 6), dpi=100)
    ax.scatter(df_pca['pca1'], df_pca['pca2'], alpha=0.5, s=5)
    ax.set_xlabel('Principal Component 1')
    ax.set_ylabel('Principal Component 2')
    ax.set_title(plotTitle if plotTitle else 'PCA 2D Decomposition')
    ax.grid(True)
    plt.tight_layout()
    plt.show()

    return df_pca


def correlationPlot(df, title="Correlation plot"):
    if 'Date' in df.columns:
        df = df.drop('Date', axis=1, inplace=False)

    corr = df.corr()
    fig, ax = plt.subplots(1, 1, figsize=(10, 8), dpi=100)
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=ax)
    ax.set_title(title)
    plt.tight_layout()
    plt.show()


def correlationDuoPlot(df1, df2, title1="Correlation plot 1", title2="Correlation plot 2"):
    if 'Date' in df1.columns:
        df1 = df1.drop('Date', axis=1, inplace=False)
    if 'Date' in df2.columns:
        df2 = df2.drop('Date', axis=1, inplace=False)

    corr1 = df1.corr()
    corr2 = df2.corr()

    fig, axes = plt.subplots(1, 2, figsize=(18, 7), dpi=100)
    sns.heatmap(corr1, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=axes[0])
    axes[0].set_title(title1)
    sns.heatmap(corr2, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=axes[1])
    axes[1].set_title(title2)
    plt.tight_layout()
    plt.show()


def correlationDifferencePlot(df1, df2, title="Correlation difference plot"):
    if 'Date' in df1.columns:
        df1 = df1.drop('Date', axis=1, inplace=False)
    if 'Date' in df2.columns:
        df2 = df2.drop('Date', axis=1, inplace=False)

    corr1 = df1.corr()
    corr2 = df2.corr()
    diff = corr1 - corr2

    fig, ax = plt.subplots(1, 1, figsize=(10, 8), dpi=100)
    sns.heatmap(diff, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=ax)
    ax.set_title(title)
    plt.tight_layout()
    plt.show()


def valueDistribution(df, traintime, testtime, columnDescriptions, columnUnits):
    df_train, df_test = utilities.getTestTrainSplit(df, traintime, testtime)

    for column in df.columns:
        fig, axes = plt.subplots(1, 2, figsize=(12, 3), dpi=100)
        desc = columnDescriptions.get(column, column) if columnDescriptions else column
        unit = columnUnits.get(column, '') if columnUnits else ''

        axes[0].hist(df_train[column], bins=50, alpha=0.7, label='Train', color='#2ca25f')
        axes[0].hist(df_test[column], bins=50, alpha=0.7, label='Test', color='#e34a33')
        axes[0].set_title(f'{desc} - Distribution')
        axes[0].set_xlabel(unit)
        axes[0].legend()

        axes[1].plot(df[column], alpha=0.7, color='#000080')
        axes[1].set_title(f'{desc} - Time series')
        axes[1].set_ylabel(unit)

        plt.tight_layout()
        plt.show()


def pairplot(df):
    if 'Date' in df.columns:
        df = df.drop('Date', axis=1, inplace=False)
    sns.pairplot(df, diag_kind='kde')
    plt.show()


def scatterplot(df):
    if 'Date' in df.columns:
        df = df.drop('Date', axis=1, inplace=False)
    columns = df.columns
    n = len(columns)
    fig, axes = plt.subplots(n, n, figsize=(3 * n, 3 * n), dpi=80)
    for i in range(n):
        for j in range(n):
            if i == j:
                axes[i, j].hist(df[columns[i]], bins=30, alpha=0.7)
            else:
                axes[i, j].scatter(df[columns[j]], df[columns[i]], alpha=0.3, s=3)
            if i == n - 1:
                axes[i, j].set_xlabel(columns[j])
            if j == 0:
                axes[i, j].set_ylabel(columns[i])
    plt.tight_layout()
    plt.show()
