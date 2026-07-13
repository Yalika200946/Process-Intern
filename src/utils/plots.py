import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

np.random.seed(100)


def getPlotColors():
    return [
        '#000080',
        '#2ca25f',
        '#8856a7',
        '#43a2ca',
        '#e34a33',
        '#636363',
        '#663300',
        '#003300',
        '#ff3399',
        '#99d8c9',
        '#9ebcda',
        '#fdbb84',
        '#c994c7',
        'darkgreen',
        'darkred',
        'darkgrey',
    ]


def plotDataColumnSingle(dfindex, plt, column, data, columnDescriptions=None, color='darkgreen', interpoldeg=3):
    fig, ax = plt.subplots(1, 1, figsize=(10, 3), dpi=100)
    ax.set_xlabel('Date')
    if columnDescriptions:
        ax.set_ylabel(columnDescriptions[column])
        ax.set_title("Deviation for " + columnDescriptions[column])
    else:
        ax.set_ylabel(column)
        ax.set_title("Deviation for " + column)
    ax.plot(dfindex, data, color=color, label="Data")
    ax.tick_params(axis='y', labelcolor=color)
    ax.grid(True, axis='y')

    z = np.polyfit(range(len(data)), data, interpoldeg)
    p = np.poly1d(z)
    func = p(range(len(data)))
    ax.plot(dfindex, func, color='black', label="Pol.fit")

    fig.subplots_adjust(right=0.7)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0., prop={'size': 10})
    fig.autofmt_xdate()


def plotColumns(
        dfindex,
        plt,
        args,
        desc="",
        columnDescriptions=None,
        trainEndStr=None,
        columnUnits=None,
        alpha=0.8,
        interpol=False,
        interpoldeg=3,
    ):
    fig, ax = plt.subplots(1, 1, figsize=(10, 3), dpi=100)
    ax.set_xlabel('Date')
    for i, arg in enumerate(args):
        label, column, data, color = arg

        ax.set_title((desc + "\n" + columnDescriptions[column]) if columnDescriptions else (desc + "\n" + column))
        ax.set_ylabel(columnUnits[column] if columnUnits is not None else "")

        if color is not None:
            ax.plot(dfindex, data, color=color, label=label, alpha=alpha)
        else:
            ax.plot(dfindex, data, label=label, alpha=alpha)

    if interpol:
        for i, arg in enumerate(args):
            label, column, data, color = arg
            z = np.polyfit(range(len(data)), data, interpoldeg)
            p = np.poly1d(z)
            func = p(range(len(data)))
            if color is not None:
                ax.plot(dfindex, func, color=color, label="Pol. fit, " + label, alpha=1.0)
            else:
                ax.plot(dfindex, func, label="Pol. fit, " + label, alpha=1.0)

    if trainEndStr:
        for i, trainEndString in enumerate(trainEndStr):
            ax.axvline(
                x=pd.to_datetime(trainEndString, dayfirst=True),
                color='black' if i % 2 == 0 else 'blue',
                label='start training' if i % 2 == 0 else 'end training'
            )
    ax.tick_params(axis='y')
    ax.grid(True, axis='y')

    fig.subplots_adjust(right=0.7)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0., prop={'size': 10})
    fig.autofmt_xdate()


def plotModelPredictions(
        plt,
        deviationsList,
        columnsList,
        indexColumn,
        columnDescriptions,
        columnUnits,
        traintime,
        interpol=False,
    ):
    colors = getPlotColors()

    for i, columns in enumerate(columnsList):
        name = columns['name']
        prediction = columns['prediction']
        actual = columns['actual']
        targetColumns = columns['targetColumns']

        for j, targetCol in enumerate(targetColumns):
            pred_col = prediction[:, j] if len(prediction.shape) > 1 else prediction
            act_col = actual[:, j] if len(actual.shape) > 1 else actual

            plotColumns(
                indexColumn,
                plt,
                [
                    ["Actual", targetCol, act_col, colors[0]],
                    ["Predicted (" + name + ")", targetCol, pred_col, colors[1]],
                ],
                desc="Prediction: " + name,
                columnDescriptions=columnDescriptions,
                columnUnits=columnUnits,
            )

        dev = deviationsList[i]
        for j, targetCol in enumerate(targetColumns):
            dev_col = dev[:, j] if len(dev.shape) > 1 else dev
            plotDataColumnSingle(
                indexColumn,
                plt,
                targetCol,
                dev_col,
                columnDescriptions=columnDescriptions,
                color=colors[4],
            )


def plotModelScores(plt, modelNames, metrics_train, metrics_test):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), dpi=100)

    x = np.arange(len(modelNames))
    width = 0.35

    train_r2 = [m[0] for m in metrics_train]
    test_r2 = [m[0] for m in metrics_test]

    axes[0].bar(x - width / 2, train_r2, width, label='Train R2')
    axes[0].bar(x + width / 2, test_r2, width, label='Test R2')
    axes[0].set_ylabel('R2 Score')
    axes[0].set_title('Model R2 Scores')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(modelNames, rotation=45, ha='right')
    axes[0].legend()

    test_mae = [m[3] for m in metrics_test]
    axes[1].bar(x, test_mae, width, label='Test MAE', color='#e34a33')
    axes[1].set_ylabel('MAE')
    axes[1].set_title('Model MAE Scores')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(modelNames, rotation=45, ha='right')

    fig.tight_layout()
    plt.show()


def plotTrainingHistory(history, title="Training History"):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), dpi=100)

    axes[0].plot(history.history['loss'], label='Train Loss')
    if 'val_loss' in history.history:
        axes[0].plot(history.history['val_loss'], label='Val Loss')
    axes[0].set_title(title + ' - Loss')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].legend()

    if 'mean_absolute_error' in history.history:
        axes[1].plot(history.history['mean_absolute_error'], label='Train MAE')
        if 'val_mean_absolute_error' in history.history:
            axes[1].plot(history.history['val_mean_absolute_error'], label='Val MAE')
    axes[1].set_title(title + ' - MAE')
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('MAE')
    axes[1].legend()

    fig.tight_layout()
    plt.show()
